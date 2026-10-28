"""Markdown export, written for a strategist reading fast.

Front: the brand's territories and the opportunities at a glance. Then one
section per opportunity: what people feel (in their words), why it's unnamed,
why the brand can speak to it, and the ideas from close-to-home to out-there.
The workings (scores, full evidence, how we got here) go in an appendix.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from .models import Collision, Run, Signal, Source, Space

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
    q = re.sub(r"^(search|read|key text|open question)\s*:\s*", "", q.strip(), flags=re.I)
    return f"[{q}](https://www.google.com/search?q={quote_plus(q)})"


def _brand(run: Run) -> str:
    return run.config.brand.upper() if run.config.brand else "the brand"


def weird_label(w: float) -> str:
    return "close to home" if w < 4 else "a stretch" if w < 7 else "out there"


def best_quotes(run: Run, sp: Space, n: int = 3) -> list[Signal]:
    sigs = [s for s in (run.signal(i) for i in sp.signal_ids) if s and s.verbatim]
    return sorted(sigs, key=lambda s: s.emotional_weight, reverse=True)[:n]


def render_idea(run: Run, sp: Space, c: Collision, n: int) -> str:
    latent = {l.name: l for l in sp.latent}
    lc = latent.get(c.latent_name)
    title = c.title or c.oblique_strategy
    out = [f"#### {n}. {title}",
           f"*{weird_label(c.surprise)} · weirdness {c.surprise:g}/10 · {_brand(run)} fit {c.brand_fit:g}/10*", "",
           f"> **{c.oblique_strategy}**", "", c.mad_thought, ""]
    if c.borrowed_from:
        out.append(f"- **Borrowed from:** {c.borrowed_from}" + (f" ({_link(lc.source)})" if lc and lc.source else ""))
    elif not c.latent_name:
        out.append("- **Borrowed from:** nothing; straight from the evidence.")
    if c.bridge:
        out.append(f"- **Why it fits:** {c.bridge}")
    out.append(f"- **For {_brand(run)}:** {c.value_exchange}")
    if c.coinage:
        out.append(f"- **Words for it:** {', '.join(c.coinage)}" + (f". {c.coinage_gloss}" if c.coinage_gloss else ""))
    if c.cannes_echo:
        out.append(f"- **Cannes echo:** {c.cannes_echo}")
    out.append(f"- **Risk:** {c.risk_note}")
    if c.dig_deeper:
        out.append("- **Dig deeper:** " + "; ".join(_search(d) for d in c.dig_deeper))
    ev = [s for s in (run.signal(i) for i in c.signal_ids) if s]
    if ev:
        out.append("- **Rests on:** " + ", ".join(_link(s.source) for s in ev))
    return "\n".join(out)


def render_space(run: Run, sp: Space, n: int) -> str:
    out = [f"## {n}. {sp.working_name}", "", f"> *\"{sp.unnamed_need}\"*", ""]
    if sp.near_miss and sp.scores:
        out += [f"_Near miss: scored below the bar ({sp.scores.cultural_distance:.1f} x {sp.scores.need_intensity:.1f}); included so you have something to judge._", ""]
    if sp.picked:
        out += ["_You chose to dive into this one, overruling its scores._", ""]
    if run.config.brand:
        out += [f"**Territory:** {sp.territory or 'unassigned'} · **{_brand(run)} fit:** {sp.brand_fit:g}/10", ""]
        if sp.right_to_play:
            out += [f"**Why {_brand(run)} can speak to it:** {sp.right_to_play}", ""]
    out += [f"**The tension:** {sp.pull_a} But {sp.pull_b[0].lower() + sp.pull_b[1:] if sp.pull_b else ''}", "",
            f"**Why nobody's named it:** {sp.why_unnamed}", ""]
    quotes = best_quotes(run, sp)
    if quotes:
        out += ["**In their words:**"] + [f"- \"{q.verbatim}\" ({_link(q.source)})" for q in quotes] + [""]
    out.append(f"**Conscience verdict:** {VERDICT_LABEL[sp.verdict.status]}"
               + (f" ({sp.verdict.by}): {sp.verdict.note}" if sp.verdict.status != "pending" else ""))
    if sp.collisions:
        out += ["", f"### Ideas, close to home → out there ({len(sp.collisions)})", ""]
        out += [render_idea(run, sp, c, i) + "\n" for i, c in enumerate(sp.collisions, 1)]
    if sp.conscience:
        cb = sp.conscience
        out += ["### Gives or takes? (for you to judge; the engine doesn't decide)",
                f"- **Gives:** {cb.gives}", f"- **Takes:** {cb.takes}",
                f"- **Who's exposed:** {cb.who_is_vulnerable}",
                f"- **How a brand could get it wrong:** " + "; ".join(cb.exploitation_vectors),
                f"- **The honest version:** {cb.honest_version}",
                "- **Ask yourself:**"] + [f"  - {q}" for q in cb.questions_for_operator]
    return "\n".join(out)


def render_appendix(run: Run, sp: Space, n: int) -> str:
    sc = sp.scores
    out = [f"### A{n}. {sp.working_name}", ""]
    if sc:
        out += [f"- Unnamed-ness {sc.cultural_distance:.1f}/10 x need {sc.need_intensity:.1f}/10 = {sc.product:.0f}/100.",
                f"- How named it already is: {sc.distance_rationale}",
                f"- How strongly it's felt: {sc.need_rationale}"]
        if sc.existing_names:
            out.append("- Closest existing names: " + "; ".join(
                f"**{x.term}** ({x.closeness})" + (f" {_link(x.source)}" if x.source else "") for x in sc.existing_names))
    out += ["", "**All evidence:**"]
    for sid in sp.signal_ids:
        s = run.signal(sid)
        if s:
            q = f' "{s.verbatim}"' if s.verbatim else ""
            out.append(f"- {s.source.platform} · {s.kind.replace('_', ' ')}: {s.observation}{q} {_link(s.source)}")
    out += ["", render_trail(run, sp)]
    return "\n".join(out)


def render_trail(run: Run, sp: Space) -> str:
    """The process, step by step, so someone else can retrace it and dig further."""
    agents = [a for a in run.agents if a.space_id == sp.id]
    score_qs = list(dict.fromkeys(q for a in agents if a.stage == "score" for q in a.queries))
    dive_qs = list(dict.fromkeys(q for a in agents if a.stage == "latent" for q in a.queries))
    out = ["**How we got here:**", ""]
    out.append(f"1. **Tension named** from {len(sp.signal_ids)} pieces of evidence.")
    check = "No established name found."
    if score_qs:
        check += " Searches run: " + "; ".join(_search(q) for q in score_qs)
    out.append(f"2. **Name check.** " + ("See closest existing names above." if sp.scores and sp.scores.existing_names else check))
    n = 3
    if sp.skeleton:
        out.append(f"{n}. **The shape of it:** {sp.skeleton}")
        n += 1
    if sp.seed_domains:
        banned = f" Ruled out as clichés: {', '.join(sp.banned_obvious)}." if sp.banned_obvious else ""
        out.append(f"{n}. **Fields searched for borrowed ideas:** {', '.join(sp.seed_domains)}, plus close-to-home and wildcard picks.{banned}")
        n += 1
    if sp.latent:
        out.append(f"{n}. **Borrowed ideas fact-checked:**" + (" searches run: " + "; ".join(_search(q) for q in dive_qs) if dive_qs else ""))
        out += [f"   - {'✓' if c.verified else '✗'} {c.name}: "
                + (f"{c.mechanism} {_link(c.source)}" if c.verified else f"dropped. {c.note}") for c in sp.latent]
    return "\n".join(out)


def render(run: Run, brief_only: bool = False) -> str:
    cfg = run.config
    title = " · ".join(x for x in [cfg.brand.upper() if cfg.brand else "", cfg.focus or "open scan"] if x)
    head = [f"# Culture Crash: {title}", ""]
    if run.demo:
        head += ["> **DEMO DATA.** Illustrative only. Tension signals are invented examples, not live research. Far concepts link to real reference pages.", ""]
    head += [f"_{run.stats.get('signals', len(run.signals))} pieces of evidence from {run.stats.get('sources', len(run.sources))} sources · "
             f"{cfg.market} · last {cfg.recency_days} days · run {run.id}_", ""]
    if run.territory:
        t = run.territory
        head += ["## Where " + _brand(run) + " can play", "", t.summary, "",
                 "- **Core:** " + "; ".join(x.name for x in t.territories if x.core),
                 "- **Adjacent:** " + "; ".join(x.name for x in t.territories if not x.core), ""]

    shortlisted = [s for s in run.spaces if s.shortlisted]
    if brief_only:
        shortlisted = [s for s in shortlisted if s.verdict.status == "gives"]
    if shortlisted:
        head += ["## The opportunities", ""]
        for i, s in enumerate(shortlisted, 1):
            fit = f" · fit {s.brand_fit:g}/10" if cfg.brand else ""
            head.append(f"{i}. **{s.working_name}**: \"{s.unnamed_need}\" ({len(s.collisions)} ideas{fit})")
        head.append("")
    head += ["_Every opportunity passes a human gate: does naming this give people something, or take something from them?_", ""]

    body = [render_space(run, s, i) for i, s in enumerate(shortlisted, 1)]
    if not body:
        body = ["_No opportunity has been cleared as 'gives' yet._" if brief_only else "_Nothing cleared the bar this run._"]
    if brief_only:
        withheld = sum(1 for s in run.spaces if s.shortlisted and s.verdict.status != "gives")
        if withheld:
            body.append(f"_{withheld} opportunit{'y' if withheld == 1 else 'ies'} withheld: pending, unsure or blocked at the conscience gate._")
        return "\n".join(head) + "\n" + "\n\n---\n\n".join(body) + "\n"

    appendix = ["# Appendix: the workings", ""] + [render_appendix(run, s, i) + "\n" for i, s in enumerate(shortlisted, 1)]
    rest = [s for s in run.spaces if not s.shortlisted]
    if rest:
        appendix += ["### Tensions found but not taken further", "", "| Tension | Unnamed-ness | Need | Why not |", "|---|---|---|---|"]
        for s in rest:
            sc = s.scores
            appendix.append(f"| {s.working_name}: \"{s.unnamed_need}\" | {sc.cultural_distance:.1f} | {sc.need_intensity:.1f} | {s.discard_reason} |"
                            if sc else f"| {s.working_name} | - | - | {s.discard_reason} |")
    body.append("\n".join(appendix))
    return "\n".join(head) + "\n" + "\n\n---\n\n".join(body) + "\n"
