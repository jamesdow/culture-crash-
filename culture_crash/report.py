"""Markdown export: per space, the unnamed need, the evidence, the gap, the
collisions, the value exchange and the conscience verdict."""

from __future__ import annotations

from urllib.parse import quote_plus

from .models import Run, Source, Space

VERDICT_LABEL = {
    "pending": "PENDING - not yet judged by a person",
    "gives": "GIVES - cleared by operator",
    "takes": "TAKES - blocked by operator",
    "unsure": "UNSURE - operator wants more evidence",
}


def _link(src: Source | None) -> str:
    if not src:
        return "(no source)"
    title = (src.title or src.url).replace("[", "(").replace("]", ")")
    if not src.url:
        return f"_{title}_"
    return f"[{title}]({src.url})"


def _search(q: str) -> str:
    return f"[{q}](https://www.google.com/search?q={quote_plus(q)})"


def render_trail(run: Run, sp: Space) -> str:
    """The process, step by step, so someone else can retrace it and dig further."""
    agents = [a for a in run.agents if a.space_id == sp.id]
    score_qs = [q for a in agents if a.stage == "score" for q in a.queries]
    dive_qs = [q for a in agents if a.stage == "latent" for q in a.queries]
    sigs = [s for s in (run.signal(i) for i in sp.signal_ids) if s]
    out = ["### How we got here", ""]
    out.append(f"1. **Evidence.** {len(sigs)} signals ({', '.join(sorted({s.kind for s in sigs}))}) from "
               f"{', '.join(sorted({s.source.platform for s in sigs}))}; each is linked under Evidence.")
    out.append(f"2. **Tension named.** {sp.pull_a} <-> {sp.pull_b}. {sp.why_unnamed}")
    names = sp.scores.existing_names if sp.scores else []
    check = "Closest existing names: " + "; ".join(f"{n.term} {_link(n.source) if n.source else ''}".strip() for n in names) + "." if names else "No established name found."
    if score_qs:
        check += " Searches run: " + "; ".join(_search(q) for q in score_qs)
    out.append(f"3. **Name check.** {check}")
    n = 4
    if sp.skeleton:
        out.append(f"{n}. **Skeleton.** {sp.skeleton}")
        n += 1
    if sp.seed_domains:
        banned = f" Banned as too obvious: {', '.join(sp.banned_obvious)}." if sp.banned_obvious else ""
        out.append(f"{n}. **Far fields drawn.** {', '.join(sp.seed_domains)}.{banned}")
        n += 1
    if sp.latent:
        out.append(f"{n}. **Concepts fact-checked.**" + (" Searches run: " + "; ".join(_search(q) for q in dive_qs) if dive_qs else ""))
        out += [f"   - {'✓' if c.verified else '✗'} {c.name} ({c.domain}): "
                + (f"{c.mechanism} {_link(c.source)}" if c.verified else f"rejected. {c.note}") for c in sp.latent]
        n += 1
    if sp.collisions:
        out.append(f"{n}. **Collision.** Each verified concept was forced against the tension; see the cards above.")
    return "\n".join(out)


def render_space(run: Run, sp: Space) -> str:
    sc = sp.scores
    out = [f"## {sp.working_name}", ""]
    if sp.near_miss and sp.scores:
        out += [f"> **Near miss:** scored below the bar ({sp.scores.cultural_distance:.1f} x {sp.scores.need_intensity:.1f}, needing {run.config.band:g} on each). Included so the run isn't empty.", ""]
    if sp.picked:
        out += ["> **Picked by the operator,** overruling its scores.", ""]
    out.append(f"> **Unnamed need:** {sp.unnamed_need}")
    out.append("")
    out.append(f"**Conscience verdict:** {VERDICT_LABEL[sp.verdict.status]}"
               + (f" ({sp.verdict.by}, {sp.verdict.at}): {sp.verdict.note}" if sp.verdict.status != "pending" else ""))
    out.append("")
    out.append(f"**The tension:** {sp.pull_a} <-> {sp.pull_b}")
    if sp.skeleton:
        out.append(f"\n**Skeleton:** _{sp.skeleton}_")
    if sc:
        out += ["", "### Scores",
                f"- Cultural distance **{sc.cultural_distance:.1f}** x need intensity **{sc.need_intensity:.1f}** = **{sc.product:.0f}** / 100 ({sp.quadrant})",
                f"- Need: model {sc.need_model:.1f}, evidence {sc.need_features:.1f} " + str(sc.feature_breakdown),
                "", "### The cultural gap", sc.distance_rationale, "", f"_Why it's unnamed:_ {sp.why_unnamed}"]
        if sc.existing_names:
            out.append("\nClosest existing names:")
            for n in sc.existing_names:
                out.append(f"- **{n.term}**: {n.closeness} {_link(n.source) if n.source else ''}")
        out += ["", f"_Need:_ {sc.need_rationale}"]

    out += ["", "### Evidence"]
    for sid in sp.signal_ids:
        s = run.signal(sid)
        if s:
            q = f' - "{s.verbatim}"' if s.verbatim else ""
            out.append(f"- `{s.id}` **{s.kind}** · {s.source.platform} (weight {s.emotional_weight}): {s.observation}{q} - {_link(s.source)}")

    if sp.collisions:
        out += ["", "### Collisions"]
        latent = {c.name: c for c in sp.latent}
        for c in sp.collisions:
            lc = latent.get(c.latent_name)
            out += ["", f"#### ■ {c.oblique_strategy}",
                    f"*Mad factor {c.mad_factor:.1f} (surprise {c.surprise:g}, coherence {c.coherence:g})*", "",
                    c.mad_thought, "",
                    f"- **Bridge:** {c.bridge}",
                    f"- **Language for it:** {', '.join(c.coinage)}: {c.coinage_gloss}",
                    f"- **Value exchange:** {c.value_exchange}",
                    f"- **Risk:** {c.risk_note}",
                    *([f"- **Dig deeper:** " + "; ".join(_search(d) for d in c.dig_deeper)] if c.dig_deeper else []),
                    f"- **Far concept:** {c.latent_name}" + (f" ({lc.domain}) - {_link(lc.source)}" if lc else ""),
                    "- **Tension evidence:** " + ", ".join(
                        f"{_link(s.source)}" for s in (run.signal(i) for i in c.signal_ids) if s)]
    if sp.conscience:
        cb = sp.conscience
        out += ["", "### Conscience brief (for the operator; the engine does not decide)",
                f"- **Gives:** {cb.gives}", f"- **Takes:** {cb.takes}",
                f"- **Who is vulnerable:** {cb.who_is_vulnerable}",
                f"- **Exploitation vectors:** " + "; ".join(cb.exploitation_vectors),
                f"- **Honest version:** {cb.honest_version}",
                "- **Questions:**"] + [f"  - {q}" for q in cb.questions_for_operator]
    out += ["", render_trail(run, sp)]
    return "\n".join(out)


def render(run: Run, brief_only: bool = False) -> str:
    cfg = run.config
    head = [f"# Culture Crash - run {run.id}", ""]
    if run.demo:
        head += ["> **DEMO DATA.** Illustrative only. Tension signals are invented examples, not live research. Far concepts link to real reference pages.", ""]
    head += [f"- Focus: {cfg.focus or 'open'} | Brand lens: {cfg.brand or 'none'} | Market: {cfg.market} | Window: {cfg.recency_days} days",
             f"- Stats: " + ", ".join(f"{k} {v}" for k, v in run.stats.items()),
             *( [f"- Reached via: " + "; ".join(f"{k}: {v}" for k, v in run.routes.items())] if run.routes else [] ),
             "", "_Every shortlisted space passes a human gate with one question: does naming this give people something, or take something from them?_", ""]

    shortlisted = [s for s in run.spaces if s.shortlisted]
    if brief_only:
        cleared = [s for s in shortlisted if s.verdict.status == "gives"]
        withheld = len(shortlisted) - len(cleared)
        body = [render_space(run, s) for s in cleared] or ["_No space has been cleared by an operator yet._"]
        if withheld:
            body.append(f"\n_{withheld} shortlisted space(s) withheld: pending, unsure or blocked at the conscience gate._")
        return "\n".join(head) + "\n" + "\n\n---\n\n".join(body) + "\n"

    body = [render_space(run, s) for s in shortlisted] or ["_Nothing cleared both bars this run._"]
    rest = [s for s in run.spaces if not s.shortlisted]
    if rest:
        tail = ["", "---", "", "## Discarded spaces", "", "| Space | Distance | Need | Score | Why |", "|---|---|---|---|---|"]
        for s in rest:
            sc = s.scores
            tail.append(f"| {s.working_name} | {sc.cultural_distance:.1f} | {sc.need_intensity:.1f} | {sc.product:.0f} | {s.discard_reason} |"
                        if sc else f"| {s.working_name} | - | - | - | {s.discard_reason} |")
        body.append("\n".join(tail))
    return "\n".join(head) + "\n" + "\n\n---\n\n".join(body) + "\n"
