# Culture Crash

*A cultural tension engine. It finds spaces where lived experience is running ahead of the culture's language for it, then collides each one with a far, improbable concept to produce Oblique Strategy-style provocations. Every claim links back to a source.*

## What it does

```
 scan ──► cluster ──► score ──► shortlist ──► latent dive ──► collide ──► conscience brief ──► HUMAN GATE
 web +     unnamed     distance   both bars     far seeded      oblique      gives / takes      gives? takes?
 Reddit    needs       × need     must clear    domains +       cards +      exposure,          (only a person
                                               verification     coinage      questions          can answer)
```

1. **Scan.** It runs five parallel web-search hunts, one per tell: emerging **slang**, **workarounds**, **over-intense micro-communities**, **low-grade shame** and **rising friction**. A sixth job harvests Reddit directly, using top posts from everyday-life subreddits and searches for phrases such as *"is there a word for"*, *"is it weird that"* and *"don't judge me"*.
2. **Cluster** the signals into candidate spaces. A space is a felt contradiction (pull A × pull B), not a topic.
3. **Score** each space. A fresh web search checks whether the space already has a name.
   - **Cultural distance** (0–10): how far the space sits from the named vocabulary. If a legible, named trend already exists, distance is capped at 3.
   - **Need intensity** (0–10): 60% the model's judgment and 40% an evidence score computed in code. The evidence score uses signal volume, how many kinds of tell appear, whether shame is present, emotional weight and how many different sites the signals come from.
   - **Rank = distance × need.** It is a product, not a sum, so a space has to clear both bars. Spaces fall into four quadrants: *target*, *already mined*, *curiosity* or *noise*.
4. **Latent dive.** This uses a blend of two methods.
   - The model restates the tension as a domain-free **skeleton** (e.g. *"a bond that fails unless held up by something outside it"*).
   - It lists its **10 most obvious associations**, which are then **banned**.
   - It must find real, named concepts in **randomly drawn far domains** (`seeds.py`: mycology, maritime salvage law, change ringing, hermit-crab vacancy chains…), plus **wildcards** it rates as least probable.
   - Candidates are ranked by low obviousness and **fact-checked with web search**. Anything without a retrieved source is rejected.
5. **Collide.** Each verified concept is forced against the tension to make a card with these parts:
   - an **oblique strategy** (≤15 words)
   - a **mad thought**
   - the exact **bridge** (the structural mapping)
   - candidate **language** for the feeling (*"give people words for what they already feel"*)
   - a **value exchange**
   - a **risk note**

   Cards are ranked by **mad factor = surprise × coherence**, so a wild card that doesn't land ranks low.
6. **Conscience brief.** For each space the engine lays out what naming it *gives*, what it *takes*, who is vulnerable, the exploitation vectors and the honest version of the idea. **The engine never writes a verdict.** A verdict is recorded only by a person, through the UI or `culture-crash verdict`. The "cleared brief" export contains only the spaces a person judged as *gives*.

### Citation integrity

Structured steps never write URLs. They point at numbered sources (`S1`, `S2`…) that the search tool or Reddit actually returned. Code resolves those numbers and **drops anything that points elsewhere**: the run reports `ungrounded_dropped`. This rule covers tension signals, existing trend names and far concepts alike.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...        # or `ant auth login`
# optional, makes Reddit far more reliable (app-only OAuth):
export REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=...
```

## Use

```bash
culture-crash serve                         # web UI on http://127.0.0.1:8765
culture-crash demo                          # illustrative offline run, no key needed

culture-crash run                           # open scan of everyday life
culture-crash run --focus "food at work" --brand "a supermarket" --days 60 --market UK
culture-crash run --seed 42 --seeds 6 --cards 4 --effort xhigh

culture-crash list
culture-crash verdict <run_id> space-1 gives --note "gives permission, no shame hook" --by James
culture-crash export <run_id> --brief --out brief.md
```

Runs are saved as JSON (with a markdown report) in `./runs/`.

**Brand lens.** `--brand` shapes only the value exchange and the conscience brief. The scan, the scoring and the oblique strategies stay brand-blind, so the brand can't bend what gets found.

**Model and cost.** The default model is `claude-opus-5-5` at `high` effort, with server-side refusal fallback switched on. A full run makes roughly 30–45 API calls, about a third of them with web search. Expect a few dollars per run, more at `xhigh`/`max` or with a larger shortlist. This is an estimate, so measure your first runs.

## Where to tune it

| File | What it controls |
|---|---|
| `culture_crash/prompts.py` | every instruction: the five tells, scoring rubrics, the dive method, card rules, the conscience brief |
| `culture_crash/seeds.py` | the far-domain pool (add stranger, more specific domains to push distance) |
| `culture_crash/scoring.py` | evidence-feature weights, model/evidence blend, quadrants, mad factor |
| `culture_crash/reddit.py` | default subreddits and "tell" queries |

## Honest limits

- **Reddit access.** Unauthenticated Reddit JSON is often rate-limited or blocked. When it is, the engine says so and falls back to web search restricted to reddit.com. Use OAuth credentials for direct access, and follow Reddit's API terms.
- **Self-scores.** Distance, need, surprise and coherence are partly the model's own ratings. The evidence feature score and the web legibility check are the counterweights. Read the rationales, not just the numbers.
- **Synthesis is not a source.** A citation proves a signal exists, not that a space is real. That judgment, like the conscience verdict, belongs to the operator.
- **Not yet run live.** The pipeline is tested end to end with a scripted model, and the Claude calls are tested against replayed API streams. It has not yet been run against the live API.

## Tests

```bash
pytest -q
```
