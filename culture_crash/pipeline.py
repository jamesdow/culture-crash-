"""The loop: scan, cluster, score, shortlist, dive, collide, then hand to a human."""

from __future__ import annotations

import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from . import prompts as P
from .activity import agent, current
from . import scoring, seeds
from .llm import LLM, EngineError, Research
from .models import (
    BrandTerritory,
    CachedResearch,
    Territory,
    SIGNAL_KINDS,
    Collision,
    LatentConcept,
    NamedTerm,
    Run,
    Scores,
    Signal,
    Source,
    Space,
)
from .harvest import DEFAULT_SUBREDDITS, DOMAINS, PLATFORMS, HarvestSpec, Post, Unavailable, routes_for, run_chain
from .schemas import BrandTerritoryOut, ClusterResult, CollisionSet, ConscienceOut, LatentDive, LatentVerification, ScoreResult, SignalExtraction
from .store import RunStore

MAX_WORKERS = 6
NEAR_MISS_MAX = 2  # how many below-the-bar spaces to dive into when too few clear it
POST_BATCH = 20  # posts per extraction call; small batches are fast and fail independently
PLATFORM_NAMES = {"reddit": "Reddit", "tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}


# ----------------------------------------------------------------- helpers


def source_list(sources: list[Source]) -> tuple[str, dict[str, Source]]:
    lines, refs = [], {}
    for i, s in enumerate(sources, 1):
        ref = f"S{i}"
        refs[ref] = s
        date = f" ({s.date})" if s.date else ""
        lines.append(f"{ref}. {s.title or '(untitled)'} - {s.url}{date}")
    return "\n".join(lines) or "(no sources retrieved)", refs


def resolve(ref: str, refs: dict[str, Source]) -> Source | None:
    m = re.search(r"\d+", ref or "")
    return refs.get(f"S{m.group()}") if m else None


def domain(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def space_block(sp: Space) -> str:
    named = ", ".join(sp.nearest_named) or "none suggested"
    return (
        f"Working name: {sp.working_name}\n"
        f"Unnamed need: {sp.unnamed_need}\n"
        f"Pull A: {sp.pull_a}\nPull B: {sp.pull_b}\n"
        f"Why it is unnamed: {sp.why_unnamed}\n"
        f"Nearest named trends to rule out: {named}"
    )


def signals_block(signals: list[Signal]) -> str:
    out = []
    for s in signals:
        quote = f' - "{s.verbatim}"' if s.verbatim else ""
        out.append(f"[{s.id}] ({s.kind}, weight {s.emotional_weight}) {s.observation}{quote} [{domain(s.source.url)}]")
    return "\n".join(out)


# ------------------------------------------------------------------ engine


class Engine:
    def __init__(self, llm: LLM, store: RunStore, routes: Callable[[str], list] = routes_for):
        self.llm = llm
        self.store = store
        self.routes = routes
        self._territory_of: dict[str, Territory] = {}

    def _tracked(self, run: Run, label: str, stage: str, fn, *args):
        space_id = next((a.id for a in args if isinstance(a, Space)), "")
        with agent(self.store, run, label, stage, space_id):
            return fn(*args)

    def _research(self, run: Run, key: str, system: str, prompt: str, **kw) -> Research:
        """Run a search, or reuse the saved one: searches already paid for are never redone."""
        cached = run.research_cache.get(key)
        if cached:
            self._step("reading", f"Reusing {len(cached.sources)} saved search results")
            return Research(text=cached.text, sources=list(cached.sources), cited_excerpts=list(cached.cited_excerpts))
        research = self.llm.research(system, prompt, **kw)
        with self.store._lock:
            run.research_cache[key] = CachedResearch(text=research.text, sources=research.sources, cited_excerpts=research.cited_excerpts)
            self.store.save(run)
        return research

    @staticmethod
    def _step(status, text: str) -> None:
        t = current.get()
        if t:
            t.status(status, text)

    def run(self, run: Run) -> Run:
        run.status = "running"
        cfg = run.config
        self.rng = random.Random(cfg.seed if cfg.seed is not None else random.randrange(1 << 30))
        resuming = bool(run.signals)
        run.error = None
        try:
            if hasattr(self.llm, "preflight"):
                self.llm.preflight()
            if resuming:
                self.store.log(run, "resume", f"Resuming: keeping {len(run.signals)} signals and {len(run.spaces)} spaces already found.")
            # Each stage skips work already done, so a failed run can be resumed where it stopped.
            if cfg.brand and run.territory is None:
                self._tracked(run, "Brand mapper", "brand", self._brand, run)
            if not run.signals:
                self._scan(run)
            if not run.spaces:
                self._tracked(run, "Clusterer", "cluster", self._cluster, run)
            self._score(run)
            self._deepen(run)
            run.status, run.stage = "done", "done"
            n = sum(1 for s in run.spaces if s.shortlisted)
            self.store.log(run, "done", f"Finished. {n} space(s) are waiting for your conscience verdict.")
        except Exception as e:  # surface every failure on the run itself
            run.status, run.error = "error", f"{type(e).__name__}: {e}"
            self.store.log(run, "error", run.error)
        return run

    # ---- 0. brand territory ---------------------------------------------

    def _brand(self, run: Run) -> None:
        brand = run.config.brand
        self.store.log(run, "brand", f"Mapping where {brand} has a right to speak.")
        self._step("searching", f"Researching {brand}")
        research = self._research(run, "brand", P.BRAND_RESEARCH_SYSTEM, P.brand_research_prompt(brand), max_searches=4)
        self._step("thinking", "Drawing the territories to hunt in")
        out = self.llm.structured(P.BRAND_SYSTEM, P.brand_prompt(brand, research.text), BrandTerritoryOut, effort="low")
        run.territory = BrandTerritory(
            brand=brand, summary=out.summary, already_says=out.already_says,
            subreddits=[r.strip().removeprefix("r/") for r in out.subreddits if r.strip()][:8],
            territories=[Territory(name=t.name, why=t.why, search_terms=t.search_terms, core=True) for t in out.core]
            + [Territory(name=t.name, why=t.why, search_terms=t.search_terms, core=False) for t in out.adjacent],
        )
        self.store.log(run, "brand", "Core: " + "; ".join(t.name for t in run.territory.territories if t.core)
                       + ". Adjacent: " + "; ".join(t.name for t in run.territory.territories if not t.core) + ".")

    def _assign_territories(self, run: Run, jobs: list[str]) -> dict[str, Territory]:
        """Point each scout at a territory: roughly brand_core_share of them at the core, the rest adjacent."""
        terr = run.territory.territories if run.territory else []
        core, adj = [t for t in terr if t.core], [t for t in terr if not t.core]
        if not core and not adj:
            return {}
        order = list(jobs)
        self.rng.shuffle(order)
        n_core = round(len(order) * run.config.brand_core_share) if adj else len(order)
        out = {}
        for i, job in enumerate(order):
            pool = core if (i < n_core and core) or not adj else adj
            out[job] = pool[(i if i < n_core else i - n_core) % len(pool)]
        return out

    # ---- 1. scan --------------------------------------------------------

    def _scan(self, run: Run) -> None:
        cfg = run.config
        self.store.log(run, "scan", f"Scanning {', '.join(cfg.platforms)} for slang, workarounds, micro-communities, shame and friction.")
        jobs: dict[str, Callable[[], tuple[list[Signal], list[Source], int]]] = {}
        if "web" in cfg.platforms:
            for kind in SIGNAL_KINDS:
                jobs[f"web:{kind}"] = lambda k=kind: self._tracked(run, f"Web scout · {k.replace('_', ' ')}", "scan", self._scan_web, run, k)
        for platform in cfg.platforms:
            if platform != "web":
                jobs[platform] = lambda p=platform: self._tracked(run, f"{PLATFORM_NAMES[p]} scout", "scan", self._scan_platform, run, p)
        if not jobs:
            raise EngineError("Every platform is switched off, so there is nothing to scan.")
        self._territory_of = self._assign_territories(run, list(jobs))

        found: list[Signal] = []
        all_sources: dict[str, Source] = {}
        dropped = 0
        failed: dict[str, Callable] = {}
        for attempt in (1, 2):
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {pool.submit(fn): name for name, fn in jobs.items()}
                for fut in as_completed(futures):
                    name = futures[fut]
                    try:
                        sigs, srcs, drop = fut.result()
                    except Exception as e:
                        failed[name] = jobs[name]
                        self.store.log(run, "scan", f"{name}: didn't finish ({e})."
                                       + (" Retrying once the others are done." if attempt == 1 else ""))
                        continue
                    found.extend(sigs)
                    dropped += drop
                    for s in srcs:
                        all_sources.setdefault(s.url, s)
                    self.store.log(run, "scan", f"{name}: {len(sigs)} grounded signal(s) from {len(srcs)} source(s).")
            if not failed or attempt == 2:
                break
            # Second chance, on its own with no competition: saved searches are reused, so only the stalled step reruns.
            jobs, failed = dict(failed), {}
            self.store.log(run, "scan", f"Second try for {', '.join(jobs)}, reusing saved searches.")
        if failed:
            run.stats["sources_lost"] = len(failed)
            self.store.log(run, "scan", f"Still missing after a second try: {', '.join(failed)}. Their saved searches are kept on the run.")

        seen, unique = set(), []
        for s in found:
            key = (s.source.url, norm(s.observation)[:60])
            if key not in seen:
                seen.add(key)
                unique.append(s)
        for i, s in enumerate(unique, 1):
            s.id = f"sig-{i:02d}"
        run.signals = unique
        run.sources = list(all_sources.values())
        run.stats.update(sources=len(run.sources), signals=len(unique), ungrounded_dropped=dropped)
        for platform in PLATFORMS:
            n = sum(1 for s in unique if s.source.platform == platform)
            if n:
                run.stats[f"signals_{platform}"] = n
        if not unique:
            raise EngineError("No grounded signals were found. Check network access, or widen the focus.")
        self.store.log(run, "scan", f"{len(unique)} signals kept; {dropped} dropped because they couldn't be tied to a retrieved source.")

    def _ground(self, extraction: SignalExtraction, refs: dict[str, Source]) -> tuple[list[Signal], int]:
        signals, dropped = [], 0
        for e in extraction.signals:
            src = resolve(e.source_ref, refs)
            if src is None:
                dropped += 1
                continue
            signals.append(Signal(id="", kind=e.kind, observation=e.observation, verbatim=e.verbatim,
                                  emotional_weight=int(scoring.clamp(e.emotional_weight, 1, 5)), source=src))
        return signals, dropped

    def _extract(self, kind_hint: str, research: Research) -> tuple[list[Signal], int]:
        self._step("thinking", f"Turning notes from {len(research.sources)} sources into evidence")
        listing, refs = source_list(research.sources)
        # Mechanical step: low effort keeps it fast and stops it going silent for minutes.
        out = self.llm.structured(P.EXTRACT_SYSTEM, P.extract_prompt(kind_hint, research.text, listing), SignalExtraction, effort="low")
        return self._ground(out, refs)

    def _scan_web(self, run: Run, kind: str) -> tuple[list[Signal], list[Source], int]:
        self._step("searching", "Hunting the open web")
        t = self._territory_of.get(f"web:{kind}")
        research = self._research(run, f"web:{kind}", P.SCAN_SYSTEM, P.scan_prompt(kind, run.config, _tdesc(t)), max_searches=6)
        sigs, dropped = self._extract(kind, research)
        return sigs, research.sources, dropped

    def _scan_platform(self, run: Run, platform: str) -> tuple[list[Signal], list[Source], int]:
        """Direct routes first; if every one fails, Claude web search restricted to the platform's domain."""
        cfg = run.config
        t = self._territory_of.get(platform)
        subs = cfg.subreddits or (run.territory.subreddits if run.territory and run.territory.subreddits else []) + DEFAULT_SUBREDDITS[:6]
        spec = HarvestSpec(focus=(t.search_terms[0] if t and t.search_terms else cfg.focus), recency_days=cfg.recency_days,
                           subreddits=subs)
        self._step("harvesting", "Trying direct routes")
        try:
            res = run_chain(self.routes(platform), spec)
        except Unavailable as e:
            self.store.set_route(run, platform, "web search on " + ", ".join(DOMAINS[platform]))
            self.store.log(run, "scan", f"{platform}: no direct route ({e}). Using web search restricted to {', '.join(DOMAINS[platform])}.")
            self._step("searching", f"Searching {', '.join(DOMAINS[platform])}")
            research = self._research(run, platform, P.SCAN_SYSTEM, P.platform_search_prompt(platform, cfg, _tdesc(t)), max_searches=6,
                                      allowed_domains=DOMAINS[platform])
            for src in research.sources:
                src.origin = "web-search"
            sigs, dropped = self._extract("mixed (decide per finding)", research)
            return sigs, research.sources, dropped

        self.store.set_route(run, platform, res.route)
        self.store.log(run, "scan", f"{platform}: {len(res.posts)} posts via {res.route}.")
        sources = [_post_source(p, res.route) for p in res.posts]
        batches = [list(range(i, min(i + POST_BATCH, len(res.posts)))) for i in range(0, len(res.posts), POST_BATCH)]
        self._step("thinking", f"Reading {len(res.posts)} posts from {res.route}, in {len(batches)} batch(es)")
        tracker = current.get()

        def read_batch(idx: list[int]) -> tuple[list[Signal], int]:
            token = current.set(tracker)  # keep reporting to this platform's card
            try:
                _, refs = source_list([sources[i] for i in idx])
                block = "\n\n".join(
                    f"S{n}. [{res.posts[i].context}] (engagement {res.posts[i].engagement})"
                    + (f"\nTITLE: {res.posts[i].title}" if res.posts[i].title else "") + f"\nTEXT: {res.posts[i].text or '(none)'}"
                    for n, i in enumerate(idx, 1)
                )
                out = self.llm.structured(P.EXTRACT_SYSTEM, P.posts_prompt(platform, block, cfg, _tdesc(t)), SignalExtraction, effort="low")
                return self._ground(out, refs)
            finally:
                current.reset(token)

        sigs: list[Signal] = []
        dropped, failures = 0, []
        with ThreadPoolExecutor(max_workers=3) as pool:
            for fut in as_completed([pool.submit(read_batch, b) for b in batches]):
                try:
                    got, d = fut.result()
                    sigs += got
                    dropped += d
                except Exception as e:  # one slow batch costs only its own posts
                    failures.append(e)
        if failures and not sigs:
            raise failures[0]
        if failures:
            self.store.log(run, "scan", f"{platform}: {len(failures)} of {len(batches)} batches took too long and were skipped.")
        return sigs, sources, dropped

    # ---- 2. cluster -----------------------------------------------------

    def _cluster(self, run: Run) -> None:
        cfg = run.config
        self.store.log(run, "cluster", "Clustering signals into candidate spaces of unnamed need.")
        self._step("thinking", f"Finding the tensions under {len(run.signals)} signals")
        tblock = run.territory.block() if run.territory else ""
        out = self.llm.structured(P.CLUSTER_SYSTEM, P.cluster_prompt(signals_block(run.signals), cfg.max_spaces, tblock), ClusterResult)
        known = {s.id for s in run.signals}
        spaces = []
        for c in out.spaces[: cfg.max_spaces]:
            ids = [i for i in dict.fromkeys(c.signal_ids) if i in known]
            if not ids:
                continue
            spaces.append(Space(id=f"space-{len(spaces) + 1}", working_name=c.working_name, unnamed_need=c.unnamed_need,
                                pull_a=c.pull_a, pull_b=c.pull_b, why_unnamed=c.why_unnamed,
                                nearest_named=c.nearest_named, signal_ids=ids, territory=c.territory,
                                brand_fit=scoring.clamp(c.brand_fit) if cfg.brand else 5.0, right_to_play=c.right_to_play))
        if not spaces:
            raise EngineError("Clustering produced no evidenced spaces.")
        run.spaces = spaces
        run.stats["spaces"] = len(spaces)
        self.store.log(run, "cluster", f"{len(spaces)} candidate spaces.")

    # ---- 3. score -------------------------------------------------------

    def _score(self, run: Run) -> None:
        cfg = run.config
        todo = [sp for sp in run.spaces if sp.scores is None]
        if todo:
            self.store.log(run, "score", f"Scoring {len(todo)} space(s): cultural distance x need intensity.")
        for sp in todo:
            sp.discard_reason = ""
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(self._tracked, run, f"Scorer · {sp.working_name}", "score", self._score_one, run, sp): sp for sp in todo}
            for fut in as_completed(futures):
                sp = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    sp.discard_reason = f"Scoring failed: {e}"
                    self.store.log(run, "score", f"{sp.working_name}: scoring failed ({e}).")

        scored = [s for s in run.spaces if s.scores]
        rank = (lambda s: s.scores.product * (0.6 + 0.04 * s.brand_fit)) if cfg.brand else (lambda s: s.scores.product)
        targets = sorted((s for s in scored if s.quadrant == "target"), key=rank, reverse=True)
        for s in targets[: cfg.shortlist]:
            s.shortlisted = True
        for s in targets[cfg.shortlist :]:
            s.discard_reason = "In the band, but outranked; raise the shortlist size to dive into it."
        # Never come back empty-handed: if too few clear the bar, also dive into the closest,
        # clearly marked as near misses (never ones that are already named trends).
        if cfg.always_show and len(targets) < cfg.shortlist:
            room = min(NEAR_MISS_MAX, cfg.shortlist - len(targets)) - sum(1 for s in scored if s.near_miss)
            closest = sorted((s for s in scored if not s.shortlisted and not s.scores.legible_trend),
                             key=rank, reverse=True)
            for s in closest[: max(0, room)]:
                s.shortlisted, s.near_miss = True, True
                s.discard_reason = ""
            near = [s for s in scored if s.near_miss]
            if near:
                self.store.log(run, "score", ("Nothing" if not targets else f"Only {len(targets)}") + " cleared both bars "
                               f"({cfg.band:g}+ on each). Also diving into the closest: "
                               + "; ".join(f"{s.working_name} ({s.scores.cultural_distance:.1f} x {s.scores.need_intensity:.1f})" for s in near) + ".")
        run.spaces.sort(key=lambda s: s.scores.product if s.scores else -1, reverse=True)
        run.stats["shortlisted"] = sum(1 for s in run.spaces if s.shortlisted)
        if not any(s.shortlisted for s in run.spaces):
            self.store.log(run, "score", "Nothing cleared both bars. Try a different focus, a longer window, or a lower band.")
        elif targets:
            names = "; ".join(s.working_name for s in targets[: cfg.shortlist])
            self.store.log(run, "score", f"Shortlisted: {names}")

    def _score_one(self, run: Run, sp: Space) -> None:
        cfg = run.config
        self._step("searching", "Checking whether this already has a name")
        research = self.llm.research(P.SCORE_RESEARCH_SYSTEM, P.score_research_prompt(space_block(sp)), max_searches=5)
        listing, refs = source_list(research.sources)
        self._step("thinking", "Scoring distance and need")
        out = self.llm.structured(P.SCORE_SYSTEM, P.score_prompt(space_block(sp), research.text, listing), ScoreResult, effort="medium")

        sigs = [s for s in (run.signal(i) for i in sp.signal_ids) if s]
        feat, breakdown = scoring.need_features(sigs)
        need = scoring.blend_need(out.need_intensity, feat)
        distance = scoring.clamp(out.cultural_distance)
        if out.legible_trend:
            distance = min(distance, 3.0)
        sp.scores = Scores(
            cultural_distance=distance,
            distance_rationale=out.distance_rationale,
            existing_names=[NamedTerm(term=n.term, closeness=n.closeness, source=resolve(n.source_ref, refs)) for n in out.existing_names],
            legible_trend=out.legible_trend,
            need_model=scoring.clamp(out.need_intensity),
            need_features=feat,
            need_intensity=need,
            need_rationale=out.need_rationale,
            feature_breakdown=breakdown,
            product=scoring.product(distance, need),
        )
        sp.quadrant = scoring.quadrant(distance, need, cfg.band)
        if sp.quadrant != "target":
            sp.discard_reason = scoring.DISCARD_REASONS[sp.quadrant]
            if out.legible_trend:
                sp.discard_reason = "Already a legible, named trend. " + sp.discard_reason
        self.store.log(run, "score", f"{sp.working_name}: distance {distance:.1f} x need {need:.1f} = {sp.scores.product:.0f} ({sp.quadrant}).")

    # ---- 4-6. dive, collide, conscience --------------------------------

    def _deepen(self, run: Run) -> None:
        cfg = run.config
        shortlisted = [s for s in run.spaces if s.shortlisted]
        todo = [s for s in shortlisted if s.conscience is None]  # finished spaces are kept on resume
        if not todo:
            return
        used: set[str] = {d for s in shortlisted for d in s.seed_domains}
        for sp in todo:  # draw seeds up front so no two spaces share a domain
            if not sp.seed_domains:
                sp.seed_domains = seeds.draw(cfg.seeds_per_space, self.rng, exclude=used)
                used.update(sp.seed_domains)
        self.store.log(run, "latent", "Diving into latent space for far, structurally matching concepts.")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(self._tracked, run, f"Diver · {sp.working_name}", "latent", self._deepen_one, run, sp): sp for sp in todo}
            for fut in as_completed(futures):
                sp = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    self.store.log(run, "collide", f"{sp.working_name}: failed ({e}).")
        run.stats["latent_verified"] = sum(1 for s in shortlisted for c in s.latent if c.verified)
        run.stats["latent_rejected"] = sum(1 for s in shortlisted for c in s.latent if not c.verified)
        run.stats["cards"] = sum(len(s.collisions) for s in shortlisted)

    def _deepen_one(self, run: Run, sp: Space) -> None:
        cfg = run.config
        sigs = [s for s in (run.signal(i) for i in sp.signal_ids) if s]

        # 4a. dive: escape the obvious, then search the seeded far domains.
        self._step("thinking", "Diving into " + ", ".join(sp.seed_domains))
        dive = self.llm.structured(P.LATENT_SYSTEM, P.latent_prompt(space_block(sp), sp.seed_domains), LatentDive)
        sp.skeleton = dive.skeleton
        sp.banned_obvious = dive.first_thoughts
        banned = [norm(b) for b in dive.first_thoughts if norm(b)]
        fresh = [c for c in dive.candidates if not any(b and (b in norm(c.name) or norm(c.name) in b) for b in banned)]
        # Keep a spread from close-to-home to out-there: the strategist wants range, not the single weirdest.
        picks = spread(sorted(fresh, key=lambda c: c.obviousness), max(3, cfg.cards_per_space - 2))
        self.store.log(run, "latent", f"{sp.working_name}: {len(dive.candidates)} far candidates, {len(dive.candidates) - len(fresh)} banned as obvious, verifying {len(picks)}.")

        # 4b. verify: nothing far-fetched gets through without a citation.
        cand_block = "\n\n".join(f"- {c.name} ({c.domain}): {c.mechanism}" for c in picks)
        self._step("searching", f"Fact-checking {len(picks)} far concepts")
        research = self.llm.research(P.VERIFY_SYSTEM, P.verify_prompt(cand_block), max_searches=2 * len(picks))
        listing, refs = source_list(research.sources)
        checks = self.llm.structured(
            P.VERIFY_STRUCT_SYSTEM,
            f"CONCEPTS\n{cand_block}\n\nNOTES\n{research.text}\n\nSOURCES\n{listing}",
            LatentVerification,
            effort="medium",
        )
        by_name = {norm(c.name): c for c in checks.checks}
        latent: list[LatentConcept] = []  # built locally, then swapped in, so concurrent saves never see a half-built list
        for c in picks:
            chk = by_name.get(norm(c.name)) or next((v for n, v in by_name.items() if n in norm(c.name) or norm(c.name) in n), None)
            src = resolve(chk.source_ref, refs) if chk else None
            ok = bool(chk and chk.verified and src)
            latent.append(LatentConcept(
                name=c.name, domain=c.domain, from_seed=c.from_seed,
                mechanism=(chk.corrected_mechanism if chk and chk.corrected_mechanism else c.mechanism),
                structural_rhyme=c.structural_rhyme, obviousness=scoring.clamp(c.obviousness),
                verified=ok, source=src if ok else None,
                note=(chk.note if chk else "No verification returned."),
            ))
        sp.latent = latent
        verified = [c for c in latent if c.verified]
        self.store.save(run)
        if not verified:
            self.store.log(run, "latent", f"{sp.working_name}: no borrowed concept survived fact-checking; generating direct ideas only.")

        # 5. collide: many ideas, spread across weirdness, scored for brand fit.
        latent_block = "\n\n".join(
            f"- {c.name} ({c.domain})\n  What it is: {c.mechanism}\n  Shared shape: {c.structural_rhyme}" for c in verified
        ) or "(none verified: make direct ideas only)"
        tension = f"{space_block(sp)}\nThe shape of it: {sp.skeleton}"
        self._step("thinking", f"Generating ideas from {len(verified)} borrowed concept(s)")
        cards = self.llm.structured(P.COLLIDE_SYSTEM, P.collide_prompt(tension, signals_block(sigs), latent_block,
                                                                       brand_block(run, sp)), CollisionSet)
        known = set(sp.signal_ids)
        names = {c.name for c in verified}
        collisions = []
        for card in cards.cards:
            concept = card.concept_name if card.concept_name in names else ""
            w, f = scoring.clamp(card.weirdness), scoring.clamp(card.brand_fit)
            collisions.append(Collision(
                id="", title=card.title, latent_name=concept, oblique_strategy=card.provocation,
                mad_thought=card.thought, borrowed_from=card.borrowed_from if concept else "", bridge=card.why_it_fits,
                coinage=card.words_for_it, coinage_gloss=card.words_gloss, value_exchange=card.for_brand,
                risk_note=card.risk, cannes_echo=card.cannes_echo, dig_deeper=card.dig_deeper,
                surprise=w, coherence=f, brand_fit=f, mad_factor=round((w + f) / 2, 2),
                signal_ids=[i for i in card.signal_ids if i in known] or sp.signal_ids[:3],
            ))
        collisions.sort(key=lambda c: c.surprise)  # close to home first, out there last
        sp.collisions = spread(collisions, cfg.cards_per_space)  # if capped, keep the range
        for i, c in enumerate(sp.collisions, 1):
            c.id = f"{sp.id}-c{i}"
        self.store.log(run, "collide", f"{sp.working_name}: {len(sp.collisions)} ideas, from "
                       f"{min((c.surprise for c in sp.collisions), default=0):.0f} to {max((c.surprise for c in sp.collisions), default=0):.0f} on weirdness.")

        # 6. conscience brief. The verdict is left to a person.
        cards_block = "\n\n".join(f"- {c.title or c.oblique_strategy}\n  {c.mad_thought}\n  For the brand: {c.value_exchange}" for c in sp.collisions)
        self._step("thinking", "Writing the conscience brief")
        sp.conscience = self.llm.structured(P.CONSCIENCE_SYSTEM, P.conscience_prompt(space_block(sp), cards_block, cfg.brand), ConscienceOut)
        assert sp.verdict.status == "pending", "the engine must never write a conscience verdict"
        self.store.save(run)


def _post_source(p: Post, route: str) -> Source:
    date = datetime.fromtimestamp(p.created_utc, tz=timezone.utc).date().isoformat() if p.created_utc else None
    title = p.title or p.text
    title = (title[:90] + "...") if len(title) > 90 else title
    return Source(url=p.url, title=f"{p.context}: {title}" if p.context else title, date=date, origin=route)


def _tdesc(t: Territory | None) -> str | None:
    return f"{t.name} ({t.why})" if t else None


def spread(items: list, k: int) -> list:
    """Evenly spaced picks across a sorted list, so both ends and the middle are represented."""
    if len(items) <= k:
        return list(items)
    if k <= 1:
        return list(items[:k])
    step = (len(items) - 1) / (k - 1)
    return [items[round(i * step)] for i in range(k)]


def brand_block(run: Run, sp: Space) -> str:
    if not run.config.brand:
        return "NO BRAND: write for_brand for the kind of brand that could credibly do this, and score brand_fit as fit with that kind of brand."
    t = run.territory.block() if run.territory else f"Brand: {run.config.brand}."
    return (f"BRAND\n{t}\nThis tension sits in: {sp.territory or 'unassigned'}. "
            f"Right to play: {sp.right_to_play or 'not stated'}")
