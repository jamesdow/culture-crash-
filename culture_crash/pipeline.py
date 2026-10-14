"""The loop: scan, cluster, score, shortlist, dive, collide, then hand to a human."""

from __future__ import annotations

import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from . import prompts as P
from . import scoring, seeds
from .llm import LLM, EngineError, Research
from .models import (
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
from .schemas import ClusterResult, CollisionSet, ConscienceOut, LatentDive, LatentVerification, ScoreResult, SignalExtraction
from .store import RunStore

MAX_WORKERS = 6


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

    def run(self, run: Run) -> Run:
        run.status = "running"
        cfg = run.config
        self.rng = random.Random(cfg.seed if cfg.seed is not None else random.randrange(1 << 30))
        try:
            if hasattr(self.llm, "preflight"):
                self.llm.preflight()
            self._scan(run)
            self._cluster(run)
            self._score(run)
            self._deepen(run)
            run.status, run.stage = "done", "done"
            n = sum(1 for s in run.spaces if s.shortlisted)
            self.store.log(run, "done", f"Finished. {n} space(s) are waiting for your conscience verdict.")
        except Exception as e:  # surface every failure on the run itself
            run.status, run.error = "error", f"{type(e).__name__}: {e}"
            self.store.log(run, "error", run.error)
        return run

    # ---- 1. scan --------------------------------------------------------

    def _scan(self, run: Run) -> None:
        cfg = run.config
        self.store.log(run, "scan", f"Scanning {', '.join(cfg.platforms)} for slang, workarounds, micro-communities, shame and friction.")
        jobs: dict[str, Callable[[], tuple[list[Signal], list[Source], int]]] = {}
        if "web" in cfg.platforms:
            for kind in SIGNAL_KINDS:
                jobs[f"web:{kind}"] = lambda k=kind: self._scan_web(run, k)
        for platform in cfg.platforms:
            if platform != "web":
                jobs[platform] = lambda p=platform: self._scan_platform(run, p)
        if not jobs:
            raise EngineError("Every platform is switched off, so there is nothing to scan.")

        found: list[Signal] = []
        all_sources: dict[str, Source] = {}
        dropped = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(fn): name for name, fn in jobs.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    sigs, srcs, drop = fut.result()
                except Exception as e:
                    self.store.log(run, "scan", f"{name} failed: {e}")
                    continue
                found.extend(sigs)
                dropped += drop
                for s in srcs:
                    all_sources.setdefault(s.url, s)
                self.store.log(run, "scan", f"{name}: {len(sigs)} grounded signal(s) from {len(srcs)} source(s).")

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
        listing, refs = source_list(research.sources)
        out = self.llm.structured(P.EXTRACT_SYSTEM, P.extract_prompt(kind_hint, research.text, listing), SignalExtraction, effort="medium")
        return self._ground(out, refs)

    def _scan_web(self, run: Run, kind: str) -> tuple[list[Signal], list[Source], int]:
        research = self.llm.research(P.SCAN_SYSTEM, P.scan_prompt(kind, run.config), max_searches=6)
        sigs, dropped = self._extract(kind, research)
        return sigs, research.sources, dropped

    def _scan_platform(self, run: Run, platform: str) -> tuple[list[Signal], list[Source], int]:
        """Direct routes first; if every one fails, Claude web search restricted to the platform's domain."""
        cfg = run.config
        spec = HarvestSpec(focus=cfg.focus, recency_days=cfg.recency_days, subreddits=cfg.subreddits or DEFAULT_SUBREDDITS)
        try:
            res = run_chain(self.routes(platform), spec)
        except Unavailable as e:
            self.store.set_route(run, platform, "web search on " + ", ".join(DOMAINS[platform]))
            self.store.log(run, "scan", f"{platform}: no direct route ({e}). Using web search restricted to {', '.join(DOMAINS[platform])}.")
            research = self.llm.research(P.SCAN_SYSTEM, P.platform_search_prompt(platform, cfg), max_searches=8,
                                         allowed_domains=DOMAINS[platform])
            for src in research.sources:
                src.origin = "web-search"
            sigs, dropped = self._extract("mixed (decide per finding)", research)
            return sigs, research.sources, dropped

        self.store.set_route(run, platform, res.route)
        self.store.log(run, "scan", f"{platform}: {len(res.posts)} posts via {res.route}.")
        sources = [_post_source(p, res.route) for p in res.posts]
        _, refs = source_list(sources)
        block = "\n\n".join(
            f"S{i}. [{p.context}] (engagement {p.engagement})" + (f"\nTITLE: {p.title}" if p.title else "") + f"\nTEXT: {p.text or '(none)'}"
            for i, p in enumerate(res.posts, 1)
        )
        out = self.llm.structured(P.EXTRACT_SYSTEM, P.posts_prompt(platform, block, cfg), SignalExtraction, effort="medium")
        sigs, dropped = self._ground(out, refs)
        return sigs, sources, dropped

    # ---- 2. cluster -----------------------------------------------------

    def _cluster(self, run: Run) -> None:
        cfg = run.config
        self.store.log(run, "cluster", "Clustering signals into candidate spaces of unnamed need.")
        out = self.llm.structured(P.CLUSTER_SYSTEM, P.cluster_prompt(signals_block(run.signals), cfg.max_spaces), ClusterResult)
        known = {s.id for s in run.signals}
        spaces = []
        for c in out.spaces[: cfg.max_spaces]:
            ids = [i for i in dict.fromkeys(c.signal_ids) if i in known]
            if not ids:
                continue
            spaces.append(Space(id=f"space-{len(spaces) + 1}", working_name=c.working_name, unnamed_need=c.unnamed_need,
                                pull_a=c.pull_a, pull_b=c.pull_b, why_unnamed=c.why_unnamed,
                                nearest_named=c.nearest_named, signal_ids=ids))
        if not spaces:
            raise EngineError("Clustering produced no evidenced spaces.")
        run.spaces = spaces
        run.stats["spaces"] = len(spaces)
        self.store.log(run, "cluster", f"{len(spaces)} candidate spaces.")

    # ---- 3. score -------------------------------------------------------

    def _score(self, run: Run) -> None:
        cfg = run.config
        self.store.log(run, "score", "Scoring each space: cultural distance x need intensity.")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(self._score_one, run, sp): sp for sp in run.spaces}
            for fut in as_completed(futures):
                sp = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    sp.discard_reason = f"Scoring failed: {e}"
                    self.store.log(run, "score", f"{sp.working_name}: scoring failed ({e}).")

        scored = [s for s in run.spaces if s.scores]
        targets = sorted((s for s in scored if s.quadrant == "target"), key=lambda s: s.scores.product, reverse=True)
        for s in targets[: cfg.shortlist]:
            s.shortlisted = True
        for s in targets[cfg.shortlist :]:
            s.discard_reason = "In the band, but outranked; raise the shortlist size to dive into it."
        run.spaces.sort(key=lambda s: s.scores.product if s.scores else -1, reverse=True)
        run.stats["shortlisted"] = len(targets[: cfg.shortlist])
        if not targets:
            self.store.log(run, "score", "Nothing cleared both bars. That's an honest result. Try a different focus, a longer window, or a lower band.")
        else:
            names = "; ".join(s.working_name for s in targets[: cfg.shortlist])
            self.store.log(run, "score", f"Shortlisted: {names}")

    def _score_one(self, run: Run, sp: Space) -> None:
        cfg = run.config
        research = self.llm.research(P.SCORE_RESEARCH_SYSTEM, P.score_research_prompt(space_block(sp)), max_searches=5)
        listing, refs = source_list(research.sources)
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
        if not shortlisted:
            return
        used: set[str] = set()
        for sp in shortlisted:  # draw seeds up front so no two spaces share a domain
            sp.seed_domains = seeds.draw(cfg.seeds_per_space, self.rng, exclude=used)
            used.update(sp.seed_domains)
        self.store.log(run, "latent", "Diving into latent space for far, structurally matching concepts.")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(self._deepen_one, run, sp): sp for sp in shortlisted}
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
        dive = self.llm.structured(P.LATENT_SYSTEM, P.latent_prompt(space_block(sp), sp.seed_domains), LatentDive)
        sp.skeleton = dive.skeleton
        sp.banned_obvious = dive.first_thoughts
        banned = [norm(b) for b in dive.first_thoughts if norm(b)]
        fresh = [c for c in dive.candidates if not any(b and (b in norm(c.name) or norm(c.name) in b) for b in banned)]
        fresh.sort(key=lambda c: c.obviousness)
        k = max(3, cfg.cards_per_space + 2)
        picks = fresh[:k]
        wild = [c for c in fresh if not c.from_seed]
        if wild and not any(not c.from_seed for c in picks):
            picks[-1:] = [wild[0]]
        self.store.log(run, "latent", f"{sp.working_name}: {len(dive.candidates)} far candidates, {len(dive.candidates) - len(fresh)} banned as obvious, verifying {len(picks)}.")

        # 4b. verify: nothing far-fetched gets through without a citation.
        cand_block = "\n\n".join(f"- {c.name} ({c.domain}): {c.mechanism}" for c in picks)
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
            self.store.log(run, "latent", f"{sp.working_name}: no far concept survived verification, so no collisions. Re-run with a new seed.")
            return

        # 5. collide.
        latent_block = "\n\n".join(
            f"- {c.name} [{c.domain}]\n  Mechanism: {c.mechanism}\n  Rhyme: {c.structural_rhyme}" for c in verified
        )
        tension = f"{space_block(sp)}\nSkeleton: {sp.skeleton}"
        cards = self.llm.structured(P.COLLIDE_SYSTEM, P.collide_prompt(tension, signals_block(sigs), latent_block, cfg.brand), CollisionSet)
        known = set(sp.signal_ids)
        collisions = []
        for card in cards.cards:
            collisions.append(Collision(
                id="", latent_name=card.latent_name, oblique_strategy=card.oblique_strategy,
                mad_thought=card.mad_thought, bridge=card.bridge, coinage=card.coinage,
                coinage_gloss=card.coinage_gloss, value_exchange=card.value_exchange, risk_note=card.risk_note,
                surprise=scoring.clamp(card.surprise), coherence=scoring.clamp(card.coherence),
                mad_factor=scoring.mad_factor(card.surprise, card.coherence),
                signal_ids=[i for i in card.signal_ids if i in known] or sp.signal_ids[:3],
            ))
        collisions.sort(key=lambda c: c.mad_factor, reverse=True)
        sp.collisions = collisions[: cfg.cards_per_space]
        for i, c in enumerate(sp.collisions, 1):
            c.id = f"{sp.id}-c{i}"
        self.store.log(run, "collide", f"{sp.working_name}: {len(sp.collisions)} collision card(s); best mad factor {sp.collisions[0].mad_factor:.1f}." if sp.collisions else f"{sp.working_name}: no cards.")

        # 6. conscience brief. The verdict is left to a person.
        cards_block = "\n\n".join(f"- {c.oblique_strategy}\n  {c.mad_thought}\n  Value exchange: {c.value_exchange}" for c in sp.collisions)
        sp.conscience = self.llm.structured(P.CONSCIENCE_SYSTEM, P.conscience_prompt(space_block(sp), cards_block, cfg.brand), ConscienceOut)
        assert sp.verdict.status == "pending", "the engine must never write a conscience verdict"
        self.store.save(run)


def _post_source(p: Post, route: str) -> Source:
    date = datetime.fromtimestamp(p.created_utc, tz=timezone.utc).date().isoformat() if p.created_utc else None
    title = p.title or p.text
    title = (title[:90] + "...") if len(title) > 90 else title
    return Source(url=p.url, title=f"{p.context}: {title}" if p.context else title, date=date, origin=route)
