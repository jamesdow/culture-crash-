# Culture Crash

*A cultural tension engine. It finds spaces where lived experience is running ahead of the culture's language for it, then collides each one with a far, improbable concept to produce Oblique Strategy-style provocations. Every claim links back to a source.*

## What it does

```
 scan ──► cluster ──► score ──► shortlist ──► latent dive ──► collide ──► conscience brief ──► HUMAN GATE
 web +     unnamed     distance   both bars     far seeded      oblique      gives / takes      gives? takes?
 Reddit    needs       × need     must clear    domains +       cards +      exposure,          (only a person
                                               verification     coinage      questions          can answer)
```

1. **Scan.** It runs five parallel open-web hunts, one per tell: emerging **slang**, **workarounds**, **over-intense micro-communities**, **low-grade shame** and **rising friction**. In parallel it listens on **Reddit, TikTok, Instagram and YouTube**, each with a prompt written for that platform's own tells (see *Where it listens* below).
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

### Where it listens: no keys required

Every platform tries its direct routes in order. If all of them fail, it falls back to **Claude's web search restricted to that platform's domain**. That search runs on Anthropic's side, so it works from anywhere with no keys. The run records which route each platform used (shown as "Reached via" in the UI and the report).

| Platform | Routes, in order | Optional upgrade |
|---|---|---|
| **Reddit** | public JSON → old.reddit JSON → RSS feeds → [Arctic Shift](https://arctic-shift.photon-reddit.com) archive → PullPush archive → web search on reddit.com | `REDDIT_CLIENT_ID`/`SECRET` (not needed) |
| **YouTube** | Data API (if keyed) → **yt-dlp** (no key; reads top comments under recent videos) → web search on youtube.com | `YOUTUBE_API_KEY`, free from Google Cloud in about 5 minutes, more reliable than yt-dlp |
| **TikTok** | Apify scraper (captions + comments, if keyed) → web search on tiktok.com | `APIFY_TOKEN`, pay-per-result, a few cents per run |
| **Instagram** | Apify hashtag scraper (if keyed) → web search on instagram.com | `APIFY_TOKEN` |
| **Open web** | Claude web search across forums, reviews, comment sections, newsletters | none |

**Reddit without a key.** The public JSON and RSS routes usually work from a home connection and are often blocked from cloud servers. The archives are research mirrors and may lag by a day or two. In the worst case, domain-restricted web search still pulls real, citable Reddit threads.

**TikTok and Instagram without a key** run on domain-restricted web search. This finds captions, titles and indexed comment text, which is good for coinage and formats but thinner on comment-section confession. Adding `APIFY_TOKEN` is the biggest single upgrade for those two. Check each platform's terms for your use.

Cross-platform evidence counts: the evidence score includes **platform spread**, so the same feeling surfacing independently on TikTok, Reddit and YouTube scores higher than one platform shouting.

### Watching it work, and retracing it afterwards

- **Live activity panel.** While a run is going, the page shows a progress bar across the stages and a card for every agent at work: whether it's thinking, searching or writing, the search it's running right now, a snippet of its thinking, how many results it has read, and a live timer. An agent that goes quiet for more than 90 seconds is flagged.
- **"How we got here".** Each shortlisted space carries its full trail: the evidence, how the tension was named, the name check (with the exact searches run, as clickable links), the skeleton, the far fields drawn and the ideas banned as obvious, every far concept verified or rejected and why, and then the collision.
- **"Dig deeper".** Every card ends with follow-up searches, places to read and an open question, all clickable, so a strategist can pick up the thread. The exported report contains the same trail and links.
- **Nothing paid for is thrown away.** Search results are saved the moment they arrive. If a later step stalls (turning notes into evidence, say), the engine retries just that step at the end of the scan, reusing the saved searches. A platform is only marked skipped if the retry fails too, and its saved searches stay on the run.
- **`culture-crash doctor`** checks your key, then times one streamed call to tell you whether long silences are Claude thinking or your connection (often a work VPN or proxy) holding the stream back. Run it if runs keep stalling.
- **Resume.** If a run fails partway (a timeout, say), **Resume run** carries on from the stage where it stopped, keeping everything already found. On the command line: `culture-crash resume <run id>`.

### Citation integrity

Structured steps never write URLs. They point at numbered sources (`S1`, `S2`…) that the search tool or Reddit actually returned. Code resolves those numbers and **drops anything that points elsewhere**: the run reports `ungrounded_dropped`. This rule covers tension signals, existing trend names and far concepts alike.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...        # or `ant auth login`. The only thing you need.
# only if your key isn't tied to a workspace (error says "not scoped to a workspace"):
export ANTHROPIC_WORKSPACE_ID=wrkspc_...
# all optional (see "Where it listens"):
export YOUTUBE_API_KEY=...                 # free; more reliable YouTube comments than yt-dlp
export APIFY_TOKEN=...                     # richer TikTok + Instagram (captions and comments)
```

## Use

```bash
culture-crash serve                         # web UI on http://127.0.0.1:8765
culture-crash demo                          # illustrative offline run, no key needed

culture-crash run                           # open scan of everyday life
culture-crash run --focus "food at work" --brand "a supermarket" --days 60 --market UK
culture-crash run --seed 42 --seeds 6 --cards 4 --effort xhigh
culture-crash run --platforms tiktok,youtube,reddit       # listen only where you choose
culture-crash run --skip instagram

culture-crash list
culture-crash verdict <run_id> space-1 gives --note "gives permission, no shame hook" --by James
culture-crash export <run_id> --brief --out brief.md
```

Runs are saved as JSON (with a markdown report) in `./runs/`.

**Brand lens.** `--brand` shapes only the value exchange and the conscience brief. The scan, the scoring and the oblique strategies stay brand-blind, so the brand can't bend what gets found.

**Model and cost.** The default model is `claude-opus-5-5` at `high` effort, with server-side refusal fallback switched on. A full run with all five sources makes roughly 35–50 API calls, about a third of them with web search. Expect a few dollars per run, more at `xhigh`/`max` or with a larger shortlist. This is an estimate, so measure your first runs.

## What you get back

- **Where the brand can play.** With a brand set, the engine first maps its territories: core ones (where about 70% of the hunting goes, set by `brand_core_share`) and adjacent ones. Each scout is pointed at one of them.
- **Five to eight tensions,** each with: what people feel in their own words, why nobody's named it, and why the brand can speak to it (with a 0-10 brand fit). One or two strong tensions from outside the territory are kept on purpose.
- **Lots of ideas per tension** (10 by default), deliberately spread from close to home to out there. Each has a title, a provocation, the thought, what it's borrowed from (in one plain sentence), why it fits, what the brand could do, words for the feeling, a risk, and a Cannes echo when it genuinely resembles a winner.
- **The idea map** plots every idea by how out there it is (left to right) against how on-brand it is (bottom to top). Sliders filter the map and the cards together.
- **Plain English throughout.** The workings (scores, all evidence, the borrowed-idea trail) sit in a collapsed "workings" section in the app and an appendix in the report.

## Where to tune it

| File | What it controls |
|---|---|
| `culture_crash/prompts.py` | every instruction: the five tells, scoring rubrics, the dive method, card rules, the conscience brief |
| `culture_crash/seeds.py` | the far-domain pool (add stranger, more specific domains to push distance) |
| `culture_crash/scoring.py` | evidence-feature weights, model/evidence blend, quadrants, mad factor |
| `culture_crash/harvest/` | per-platform routes, default subreddits, search phrases and hashtags |
| `PLATFORM_BRIEFS` in `prompts.py` | what each platform's native tells look like |

## Honest limits

- **Direct routes are untested live.** The Reddit, YouTube and Apify routes are tested against mocked responses. They couldn't be reached from the sandbox they were built in. Any route that breaks fails over to the next one and is logged on the run, so a broken route degrades the scan but doesn't stop it.
- **Self-scores.** Distance, need, surprise and coherence are partly the model's own ratings. The evidence feature score and the web legibility check are the counterweights. Read the rationales, not just the numbers.
- **Synthesis is not a source.** A citation proves a signal exists, not that a space is real. That judgment, like the conscience verdict, belongs to the operator.
- **Not yet run live.** The pipeline is tested end to end with a scripted model, and the Claude calls are tested against replayed API streams. It has not yet been run against the live API.

## Tests

```bash
pytest -q
```
