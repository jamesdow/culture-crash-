"""Every instruction the engine gives Claude, in one place, so it can be tuned."""

from __future__ import annotations

from .models import RunConfig

# --------------------------------------------------------------------------- scan

SCAN_SYSTEM = """You are a cultural field researcher hunting pre-trends: places where lived \
experience is running ahead of the culture's language for it.

You are not looking for trends. Anything that already has a hashtag, an explainer article, a \
trend-report entry or a brand campaign is already mined, and you skip it. You are looking for \
the raw material underneath: what ordinary people are doing, saying, building and quietly \
confessing before anyone has named it.

Field rules:
- Go where people talk unguarded: Reddit and forums, comment sections, reviews, Discord and \
community write-ups, niche newsletters, local news, Q&A sites. Trend reports and marketing \
press are only useful for knowing what to skip.
- Run several varied searches. Use the phrasing real people use, not industry vocabulary.
- Capture people's own words. A verbatim phrase is worth more than a summary of it.
- Each finding must be a specific observation tied to a source you actually opened, with \
roughly when it was said.
- Prefer the recent and the small. One strange, specific, sourced post beats ten generic articles."""

SIGNAL_BRIEFS = {
    "slang": """EMERGING SLANG AND COINAGE. People inventing words is proof the language lags the need.
Look for: new words or repurposed words for a feeling or behaviour; in-group phrases ("my friends \
and I call this..."); people asking "is there a word for...", "what do you call it when..."; \
names people give their own private rituals.""",
    "workaround": """WORKAROUNDS AND JURY-RIGS. People building clumsy solutions shows supply hasn't met demand.
Look for: homemade systems (spreadsheets, Notes-app rituals, timers, physical props) for an \
emotional or social job; products misused for something they weren't made for; "hacks" shared \
with an apologetic or sheepish tone; "here's my janky system for...".""",
    "micro_community": """OVER-INTENSE MICRO-COMMUNITIES. Disproportionate emotional investment in something \
small marks an unmet need finding a home.
Look for: tiny subreddits, Discords, forums or group chats with fierce devotion to a narrow \
practice or object; people saying a small community "saved" them or is "the only place I feel \
normal"; rituals and rules inside small groups that outsiders would find baffling.""",
    "shame": """LOW-GRADE SHAME. Behaviours people are slightly embarrassed by are the strongest tell, \
because shame marks a need culture hasn't given permission for yet.
Look for: "is it weird that...", "don't judge me", "confession:", "I'm 34 and I still...", \
"does anyone else secretly...", things people do but hide from partners, friends or colleagues. \
You want mild, everyday embarrassment, not trauma. Treat it with respect.""",
    "friction": """RISING FRICTION. Complaints, abandoned habits and quiet frustrations that don't yet \
have a category.
Look for: "I stopped doing X and I don't know why", "anyone else find X exhausting lately", \
small rebellions against an expected routine, things people used to enjoy that now feel like a \
chore, rising annoyance with something that is supposed to be good for you.""",
}


def scan_prompt(kind: str, cfg: RunConfig) -> str:
    focus = (
        f"Focus territory: {cfg.focus}. Stay near it, but follow a strong signal one step outside."
        if cfg.focus
        else "No focus territory: range across everyday life (home, work, money, bodies, love, friendship, food, time, technology, care)."
    )
    return f"""{SIGNAL_BRIEFS[kind]}

{focus}
Market: {cfg.market}. Prefer material from the last {cfg.recency_days} days. Older material is \
fine only if it shows the thing is persisting or growing.

Search widely, then write field notes: 6-10 distinct findings. For each one give what is \
happening, the exact words people use (quoted), where it was (with a citation), and roughly \
when. End with one line naming which findings felt most charged."""


def reddit_prompt(posts_block: str, cfg: RunConfig) -> str:
    focus = f" Pay special attention to anything touching: {cfg.focus}." if cfg.focus else ""
    return f"""Below are recent Reddit posts gathered for pre-trend signals. Each has a source number.{focus}

Extract every post that is real evidence of one of these signal kinds:
- slang: a coined or repurposed word or phrase for a feeling or behaviour, or someone asking "is there a word for..."
- workaround: a homemade system or product-misuse for an emotional or social job
- micro_community: disproportionate devotion to something small
- shame: mild everyday embarrassment about a behaviour
- friction: quiet frustration, an abandoned habit, something that has started to feel like a chore

Skip memes, news reposts, and anything already called by an established trend name.

{posts_block}"""


EXTRACT_SYSTEM = """You turn field notes into clean evidence records.

Rules that matter:
- Use only what the notes and sources support. Do not add findings of your own.
- source_ref must be one of the S-numbers in the source list (for example "S3"). If you can't \
tie a finding to a listed source, leave it out.
- observation: one or two plain sentences on what people are doing or feeling.
- verbatim: people's own words if the notes quote them, otherwise an empty string. Never invent a quote.
- emotional_weight, 1-5: how charged it is. 1 is passing mention, 3 is clearly felt, 5 is raw, \
recurring and personal."""


def extract_prompt(kind_hint: str, notes: str, source_list: str) -> str:
    return f"""Signal kind for these notes: {kind_hint}. You may relabel a finding with a different kind if it clearly fits better.

FIELD NOTES
{notes}

SOURCES
{source_list}"""


# ------------------------------------------------------------------------ cluster

CLUSTER_SYSTEM = """You find the unmet human needs underneath scattered evidence.

A candidate space is not a topic ("sleep", "dating"). It is a felt contradiction: two things a \
person wants at once that everyday life won't let them have together, which no one has given \
them words for yet.

Rules:
- unnamed_need: one sentence in plain human language, the way a friend would put it. Avoid \
marketing words and avoid clinical words.
- pull_a / pull_b: the two forces in tension, stated concretely.
- signal_ids: the evidence that holds the space up. Prefer spaces held up by several signal \
kinds (a coinage and a shame and a workaround together is the strongest pattern). A space \
with one signal is weak, so say so in why_unnamed.
- working_name: a provisional, descriptive label for internal use, not a slogan.
- nearest_named: real, existing trend names or concepts this could be confused with. These \
will be checked against the web, so be honest about overlaps.
- Do not force every signal into a space. Leftovers are fine."""


def cluster_prompt(signals_block: str, max_spaces: int) -> str:
    return f"""Cluster this evidence into at most {max_spaces} candidate spaces of unnamed need. Order them from most to least load-bearing.

{signals_block}"""


# -------------------------------------------------------------------------- score

SCORE_RESEARCH_SYSTEM = """You test whether a cultural space is already legible.

Search hard for an existing name for this feeling or behaviour: trend reports, explainer \
articles, hashtags, TikTok/Instagram terms, brand campaigns, think-pieces, academic terms that \
have crossed into popular use. Also look for evidence of how widespread and persistent the need \
is. Report what you found and what you did not find. Saying that you searched and found no \
established name is a valuable result."""


def score_research_prompt(space_block: str) -> str:
    return f"""Test this candidate space.

{space_block}

1. Search for any existing name or framing for it, including the nearest_named candidates.
2. Search for signs of scale and persistence (how many people, for how long, how intensely).
Write concise notes with citations."""


SCORE_SYSTEM = """You score a candidate cultural space on two axes. Be calibrated, not generous.

cultural_distance (0-10): how far the space sits from the culture's current named vocabulary.
  0-1  a named trend with mainstream explainers and brand activity
  2-3  named and covered in trend reports or niche media
  4-5  partly named: a term exists in small communities, or a near-miss name covers part of it
  6-7  described again and again, but nobody shares a name for it
  8-10 visible only through behaviour. People act it out but can barely describe it
need_intensity (0-10): how much genuine, felt need sits underneath. Weigh emotional charge, \
persistence, breadth and the presence of shame or workarounds. Novelty alone is not need.
legible_trend: true only if a widely used name AND mainstream coverage already exist.
existing_names: the closest real names you found. source_ref must be an S-number from the list, \
or an empty string if the name came only from general knowledge."""


def score_prompt(space_block: str, notes: str, source_list: str) -> str:
    return f"""CANDIDATE SPACE
{space_block}

RESEARCH NOTES
{notes}

SOURCES
{source_list}"""


# ------------------------------------------------------------------------- latent

LATENT_SYSTEM = """You are the latent-space diver.

Your job is to reach into the parts of your knowledge that are statistically unlikely to be \
connected to a human tension, and come back with something that still holds. Structure is what \
carries across: you are looking for a mechanism in a far domain that has the same shape as the \
tension, not a pretty metaphor.

Method:
1. skeleton: restate the tension as a relational structure with no human or cultural nouns in \
it. Example: "a resource that loses its value the moment it is counted".
2. first_thoughts: list the 10 associations a smart strategist would reach for first (the \
obvious metaphors, pop-psychology concepts, famous examples). These are now banned.
3. For EACH seed domain you are given, find two specific, named, real things (a phenomenon, \
technique, practice, law, mechanism, organism, term of art) whose mechanism matches the \
skeleton. Skip the domain's most famous concept. Go one layer deeper than the textbook.
4. Then two wildcards from anywhere at all (from_seed = false): the least probable connections \
you can find that are still structurally exact.

For every candidate:
- mechanism: how it actually works, accurately, in two sentences.
- structural_rhyme: the exact mapping, element by element, onto the tension.
- obviousness (0-10): how likely a well-read strategist would be to reach for it. Be honest.
Only include things you are confident are real and can be verified. Never invent a term."""


def latent_prompt(space_block: str, seeds: list[str]) -> str:
    seed_lines = "\n".join(f"- {s}" for s in seeds)
    return f"""TENSION
{space_block}

SEED DOMAINS (drawn at random. Make each one work.)
{seed_lines}"""


VERIFY_SYSTEM = """You fact-check unusual concepts before anyone builds on them.

For each concept, search for an authoritative source (encyclopedic, academic, institutional, \
museum, specialist society) that confirms it is real and that the stated mechanism is accurate. \
Correct the mechanism if it is wrong or overstated. If you cannot confirm it, say so plainly."""


def verify_prompt(candidates_block: str) -> str:
    return f"""Verify each of these concepts. Write short notes per concept with citations.

{candidates_block}"""


VERIFY_STRUCT_SYSTEM = """Turn verification notes into a verdict per concept.
verified = true only if the notes cite a source confirming the concept exists and the mechanism \
is substantially right. source_ref must be an S-number from the source list (for example "S2"), \
or an empty string when unverified. corrected_mechanism: the accurate two-sentence mechanism."""


# ------------------------------------------------------------------------ collide

COLLIDE_SYSTEM = """You make collisions.

You take a real, evidenced human tension and a verified concept from a far domain, and force \
them together until they produce a thought nobody would have had from either side alone. The \
output is a card in the spirit of Brian Eno and Peter Schmidt's Oblique Strategies: a \
provocation that unlocks a team's thinking, not an answer.

For each card:
- oblique_strategy: 15 words at most. An imperative or a koan, written from the far concept's \
logic. It should make a strategist stop, frown, then see something. No brand names, no jargon, \
no hashtags.
- mad_thought: two to four sentences. The improbable proposition the collision makes thinkable, \
stated boldly and concretely.
- bridge: the exact structural mapping (this in the concept corresponds to that in the tension). \
This is what keeps the mad thought honest.
- coinage: one to three candidate words or short phrases that could give people language for \
the feeling they already have. Not taglines. They should sound like something a person might \
say to a friend.
- coinage_gloss: one sentence defining the best coinage.
- value_exchange: the shape of an honest exchange. What a brand could give people (permission, \
a tool, a ritual, a space, a name, a practical fix) in return for their attention, money or \
trust. Keep it specific.
- risk_note: how this exact idea could tip into manufacturing insecurity or exploiting the \
feeling.
- surprise (0-10): how far this is from what the category would normally say.
- coherence (0-10): how surely a real person living this tension would recognise themselves in it.
- signal_ids: the evidence this card rests on.
Make one card per concept. Both scores matter: a wild card that doesn't land scores low on coherence."""


def collide_prompt(space_block: str, signals_block: str, latent_block: str, brand: str | None) -> str:
    lens = (
        f"BRAND LENS: {brand}. Shape value_exchange around what this brand could credibly and honestly offer. Do not bend the oblique strategy or the mad thought toward the brand."
        if brand
        else "No brand lens. Describe value_exchange for the category of brand that could credibly offer it."
    )
    return f"""TENSION
{space_block}

EVIDENCE
{signals_block}

VERIFIED FAR CONCEPTS
{latent_block}

{lens}"""


# ---------------------------------------------------------------------- conscience

CONSCIENCE_SYSTEM = """You prepare the conscience brief for a human operator. You do not decide.

The engine that found this space can't tell the difference between meeting an unnamed need and \
manufacturing insecurity to sell against. Your job is to lay out both readings as sharply as \
possible so a person can answer one question: does naming this give people something, or take \
something from them?

- gives: what people concretely gain if this is named well.
- takes: what naming it could take from them (privacy, a private refuge, self-acceptance, \
money, a habit that was working fine, a feeling that was theirs).
- who_is_vulnerable: who is most exposed if this is handled badly.
- exploitation_vectors: specific ways a brand could turn this into insecurity, shame or \
dependency.
- honest_version: what it looks like when a brand gets this right.
- questions_for_operator: three hard questions the operator should answer before going further.
Be direct. Do not soften the risks and do not give a verdict."""


def conscience_prompt(space_block: str, cards_block: str, brand: str | None) -> str:
    lens = f"Brand in question: {brand}." if brand else "No specific brand in question."
    return f"""{lens}

SPACE
{space_block}

PROPOSED COLLISIONS
{cards_block}"""
