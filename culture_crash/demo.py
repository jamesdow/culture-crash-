"""An illustrative, offline run so the UI and report can be explored without an
API key. The tension signals are invented examples and are labelled as such;
the far concepts point at real reference pages."""

from __future__ import annotations

from . import scoring
from .models import (
    Collision,
    ConscienceBrief,
    LatentConcept,
    NamedTerm,
    Run,
    RunConfig,
    Scores,
    Signal,
    Source,
    Space,
)


def _sig(i: int, kind: str, obs: str, verbatim: str, weight: int, where: str) -> Signal:
    return Signal(id=f"sig-{i:02d}", kind=kind, observation=obs, verbatim=verbatim, emotional_weight=weight,
                  source=Source(url="", title=f"Illustrative example ({where}), not a real post", origin="demo"))


def _wiki(name: str, slug: str) -> Source:
    return Source(url=f"https://en.wikipedia.org/wiki/{slug}", title=f"{name} - Wikipedia", origin="demo")


SIGNALS = [
    _sig(1, "slang", "People describe owing friends a catch-up as a debt that compounds the longer it goes unpaid.", "my catch-up debt is now at payday-loan levels", 4, "Reddit post"),
    _sig(2, "workaround", "Recurring phone reminders set to message specific close friends every few weeks.", "I have a reminder that just says 'text Sam, you love Sam'", 4, "YouTube comment"),
    _sig(3, "shame", "Embarrassment at admitting a best friendship is maintained by calendar reminders.", "it feels so fake that I need an alarm to remember my best friend exists", 5, "TikTok comment"),
    _sig(4, "friction", "Dread at the phrase 'we must catch up properly', because it signals a plan that will never happen.", "'we should catch up properly' is where friendships go to die", 4, "Instagram comment"),
    _sig(5, "micro_community", "Small groups of friends who keep the same standing night at the same pub for years and protect it fiercely.", "nobody RSVPs. Thursday is just Thursday", 3, "local news feature"),
    _sig(6, "slang", "People say they are tired before an event even starts: the plan has already drained them.", "I'm pre-tired for Saturday and it's Tuesday", 4, "Reddit post"),
    _sig(7, "workaround", "Booking only refundable or cancellable options so that backing out stays possible.", "I only say yes to things I can bail on", 3, "Reddit comment"),
    _sig(8, "shame", "Feeling guilty about being relieved when someone else cancels.", "the joy when they cancel first is my most shameful emotion", 5, "TikTok comment"),
    _sig(9, "friction", "Dreading a calendar with nothing unpleasant in it, just because every slot is full.", "every single thing is nice and I still want to lie under a table", 4, "TikTok caption"),
    _sig(10, "shame", "Adults secretly learning basics they think they should already know (boiling an egg, reading a payslip, swimming).", "I'm 36 and I watched a video on how to boil an egg with the sound off so my partner wouldn't hear", 5, "TikTok comment"),
    _sig(11, "workaround", "Practising adult skills in private before doing them in front of anyone else.", "I practise phone calls to the GP in the car first", 4, "Reddit post"),
    _sig(12, "micro_community", "Tiny online groups where adults swap 'embarrassing basics' they've just learned, with fierce mutual kindness.", "this is the only place I can ask how a mortgage actually works", 4, "Reddit community"),
    _sig(13, "friction", "Rejecting polished tutorials because they assume a baseline the learner doesn't have.", "every tutorial starts at step 3", 3, "Reddit comment"),
    _sig(14, "slang", "Spending whole days in bed on purpose as self-care.", "full bed-rot sunday", 3, "TikTok caption"),
    _sig(15, "micro_community", "People collecting and swapping used hotel key cards.", "my key card binder is up to 140", 2, "Instagram post"),
]


def _space(id_, name, need, a, b, why, named, sig_ids, dist, model_need, rationale_d, rationale_n, existing=(), legible=False) -> Space:
    sigs = [s for s in SIGNALS if s.id in sig_ids]
    feat, breakdown = scoring.need_features(sigs)
    need_i = scoring.blend_need(model_need, feat)
    sp = Space(id=id_, working_name=name, unnamed_need=need, pull_a=a, pull_b=b, why_unnamed=why,
               nearest_named=list(named), signal_ids=list(sig_ids))
    sp.scores = Scores(cultural_distance=dist, distance_rationale=rationale_d, existing_names=list(existing),
                       legible_trend=legible, need_model=model_need, need_features=feat, need_intensity=need_i,
                       need_rationale=rationale_n, feature_breakdown=breakdown, product=scoring.product(dist, need_i))
    sp.quadrant = scoring.quadrant(dist, need_i, 5.5)
    if sp.quadrant != "target":
        sp.discard_reason = ("Already a legible, named trend. " if legible else "") + scoring.DISCARD_REASONS[sp.quadrant]
    return sp


def _card(sp: Space, n: int, latent: str, strategy: str, mad: str, bridge: str, coin: list[str], gloss: str,
          vx: str, risk: str, surprise: float, coherence: float, sig_ids: list[str]) -> Collision:
    return Collision(id=f"{sp.id}-c{n}", latent_name=latent, oblique_strategy=strategy, mad_thought=mad, bridge=bridge,
                     coinage=coin, coinage_gloss=gloss, value_exchange=vx, risk_note=risk, surprise=surprise,
                     coherence=coherence, mad_factor=scoring.mad_factor(surprise, coherence), signal_ids=sig_ids)


def build_demo_run(run_id: str) -> Run:
    friends = _space(
        "space-1", "Scheduled intimacy",
        "I want my closest friendships to feel effortless, but the only ones that survive are the ones I schedule like a dentist appointment.",
        "Friendship is supposed to be spontaneous and unforced", "Adult life only leaves room for what gets put in a calendar",
        "People talk about loneliness and about busyness, but not about the shame of needing a system to love someone.",
        ["friendship recession", "loneliness epidemic"], ["sig-01", "sig-02", "sig-03", "sig-04", "sig-05"],
        7.5, 8.0,
        "Loneliness is heavily named, but the specific feeling of compounding 'catch-up debt', and the shame of maintaining love with reminders, has no shared word.",
        "Five signals across all five kinds, with high emotional weight and explicit shame.",
        existing=[NamedTerm(term="friendship recession", closeness="Names the macro trend (fewer close friends), not the felt contradiction of scheduled love.")],
    )
    friends.skeleton = "A bond that is meant to hold itself up, and fails unless it is held up by something outside it."
    friends.banned_obvious = ["loneliness epidemic", "Dunbar's number", "quality time", "love languages", "social battery", "watering a plant", "bucket list", "FOMO", "digital detox", "village it takes"]
    friends.seed_domains = ["transhumance and seasonal grazing", "the Jubilee year and debt release", "bell founding and change ringing", "railway signalling"]
    friends.latent = [
        LatentConcept(name="Hefting", domain="transhumance and seasonal grazing", mechanism="Hill sheep learn the boundaries of an unfenced home range and keep to it; ewes pass the knowledge on to their lambs, so the flock holds its ground without walls.",
                      structural_rhyme="The bond (staying together) is held by inherited habit of place, not by an external enforcement device (a fence, a reminder).", obviousness=1.5, verified=True, source=_wiki("Hefting", "Hefting")),
        LatentConcept(name="Shmita", domain="the Jubilee year and debt release", mechanism="In the seventh year of the agricultural cycle in Jewish law, land lies fallow and many personal debts are released.",
                      structural_rhyme="A built-in release of accumulated obligation stops debt compounding into a reason to avoid the relationship altogether.", obviousness=2.5, verified=True, source=_wiki("Shmita", "Shmita")),
        LatentConcept(name="Change ringing", domain="bell founding and change ringing", mechanism="Ringers sound a set of tuned bells in mathematical permutations rather than melodies; each ringer follows a 'method', and the music comes from the pattern.",
                      structural_rhyme="Togetherness comes from shared pattern, not from each person deciding to show up each time.", obviousness=2.0, verified=True, source=_wiki("Change ringing", "Change_ringing")),
    ]
    friends.collisions = [
        _card(friends, 1, "Hefting", "Stop building fences. Graze the same hillside until the hill remembers you.",
              "The reminder is a fence: it works, but it tells you the friendship would wander off without it. Hefted friendships hold because of a place and a rhythm that has been learned so deeply nobody needs to decide to show up. The job isn't to remember people better, it's to make a hillside to return to.",
              "Hefted sheep = friends held by habit of place; fence = calendar reminder; passing the heft from ewe to lamb = rituals passed on to new friends and partners.",
              ["hefted", "hefted friends"], "Friends you never have to schedule, because you share a place-and-time habit that holds you.",
              "A venue, food or drink brand offers a standing 'heft': the same table, same night, kept for you indefinitely, no booking. It sells continuity, not a night out.",
              "Could become a loyalty scheme dressed up as belonging, or quietly guilt people who can't keep a standing night.", 8, 8.5, ["sig-02", "sig-03", "sig-05"]),
        _card(friends, 2, "Shmita", "Declare a jubilee: forgive every catch-up you are owed, and every one you owe.",
              "Catch-up debt compounds until it's cheaper to let the friendship lapse than to pay it back properly. A jubilee cancels it on purpose: you get to text someone after a year without the 'sorry I've been rubbish' tax. The relief is the gift.",
              "Debt release in the seventh year = a ritual release of accumulated social obligation; fallow land = a friendship allowed to rest without being lost.",
              ["catch-up jubilee", "friendship jubilee"], "A mutual, guilt-free cancelling of all the catch-ups you owe each other, so you can just start again.",
              "A messaging, card or gifting brand gives people a no-apology restart: a message form that cancels the debt and the explanation together.",
              "Turning release into a seasonal 'campaign' could commodify a tender reconciliation moment.", 8.5, 8, ["sig-01", "sig-04"]),
        _card(friends, 3, "Change ringing", "Ring the method, not the tune.",
              "Stop trying to make each meeting special. Agree a pattern and let the pattern be the music. Friendship by method beats friendship by inspiration.",
              "Method ringing = an agreed rotation of who hosts and who calls; the music of permutations = the closeness that comes from repetition, not peak moments.",
              ["method friends"], "Friends who keep each other through an agreed rotation instead of heroic one-off efforts.",
              "A food or home brand offers rotation kits: 'whose turn' rituals for small groups.", "Could make friendship feel like admin, which is the exact pain point.", 7, 6.5, ["sig-02", "sig-05"]),
    ]
    friends.conscience = ConscienceBrief(
        gives="Language that removes the shame of needing a structure to love people, and a structure that doesn't feel like admin.",
        takes="Could make people feel their friendships are deficient unless they adopt a ritual, or turn a private coping mechanism into a public performance.",
        who_is_vulnerable="Isolated people, new parents, carers and anyone whose life can't hold a standing commitment.",
        exploitation_vectors=["Selling loneliness back as a subscription", "Guilt-tripping lapsed friendships in ads", "Gamifying friendship streaks"],
        honest_version="Give people a place and a rhythm, then get out of the way. No streaks, no nudges.",
        questions_for_operator=["Would this still be worth doing if nobody ever credited the brand?", "Does it work for someone who can't afford the standing night?", "Are we naming relief, or naming a new failure?"],
    )

    pre = _space(
        "space-2", "Pre-tiredness",
        "I'm worn out by plans before they happen; the waiting costs more than the thing itself.",
        "I want a full, connected life", "Every booked plan sits on my chest from the moment I say yes",
        "Burnout and social battery are named; the specific anticipatory cost of a nice plan, and the guilty relief of cancellations, is not.",
        ["social battery", "JOMO", "anticipatory anxiety"], ["sig-06", "sig-07", "sig-08", "sig-09"],
        6.0, 7.0,
        "Adjacent terms (social battery, JOMO) cover part of it, but 'pre-tired' is still in-group coinage.",
        "Strong shame signal (relief at cancellation) and a widespread workaround (only bookable-if-cancellable).",
        existing=[NamedTerm(term="JOMO", closeness="Celebrates missing out; doesn't name the cost of a plan you actually want to go to.")],
    )
    pre.skeleton = "Load that accumulates from the moment a commitment is made, not when it is carried."
    pre.banned_obvious = ["social battery", "spoon theory", "introvert recharge", "burnout", "FOMO/JOMO", "self-care", "boundaries", "Marie Kondo", "slow living", "hygge"]
    pre.seed_domains = ["bridge expansion joints", "tardigrade cryptobiosis", "metallurgy and work hardening", "polar expedition logistics"]
    pre.latent = [
        LatentConcept(name="Expansion joint", domain="bridge expansion joints", mechanism="Deliberate gaps built into bridges and buildings absorb heat expansion and movement, so the structure doesn't crack under stress it can't avoid.",
                      structural_rhyme="Stress from a fixed commitment is absorbed by designed slack either side of it, rather than by the person.", obviousness=2.0, verified=True, source=_wiki("Expansion joint", "Expansion_joint")),
        LatentConcept(name="Annealing", domain="metallurgy and work hardening", mechanism="Heating metal and cooling it slowly relieves internal stresses built up by working it, making it less brittle.",
                      structural_rhyme="Stress built up by anticipation is released by slow, controlled exposure, not by avoidance.", obviousness=3.0, verified=True, source=_wiki("Annealing", "Annealing_(materials_science)")),
    ]
    pre.collisions = [
        _card(pre, 1, "Expansion joint", "Build the gap into the bridge, or the bridge will make its own.",
              "Pre-tiredness is a structure cracking because it has no slack. The plan isn't the problem; the plan touching everything else is. Sell the gap, not the event: the unbookable hour before and after.",
              "Thermal expansion = anticipatory load; designed gaps = protected blank time either side of plans; cracking = cancelling.",
              ["expansion hour", "a joint"], "A deliberately empty hour either side of a plan, so you can actually look forward to it.",
              "An events, travel or hospitality brand sells plans with built-in slack: late check-in, no dress code, an arrive-whenever window.",
              "Could moralise rest, or imply that people who cancel are badly designed.", 7.5, 8.5, ["sig-06", "sig-09"]),
        _card(pre, 2, "Annealing", "Heat it slowly. Cool it slower.",
              "The dread isn't telling you to cancel. It's telling you the commitment arrived too fast and too hot. Let plans arrive gradually and they stop being brittle.",
              "Work hardening = stress from back-to-back yeses; slow heating and cooling = gradual commitment (pencil, then ink).",
              ["pencil-in", "annealed plans"], "Plans that firm up slowly instead of being locked in the moment you say yes.",
              "A booking or calendar product with a 'soft yes' state that firms up by itself over time.", "A thin line between easing commitment and normalising flakiness.", 7, 7, ["sig-07", "sig-08"]),
    ]
    pre.conscience = ConscienceBrief(
        gives="Permission to want a plan and dread it at the same time, plus designs that lower the cost of saying yes.",
        takes="Could turn ordinary reluctance into a condition that needs a product, or excuse breaking commitments to people who need them.",
        who_is_vulnerable="People with anxiety disorders, for whom 'it's just pre-tiredness' could delay real help.",
        exploitation_vectors=["Medicalising normal reluctance", "Selling cancellation insurance off the back of guilt"],
        honest_version="Design plans with slack in them, and say the feeling out loud without diagnosing it.",
        questions_for_operator=["Does this risk trivialising clinical anxiety?", "Who is let down when plans get softer?", "Is the gap something we can actually give, or just say?"],
    )

    basics = _space(
        "space-3", "Secret beginners",
        "I want to learn the basic things I was supposed to know by now, without anyone finding out that I didn't.",
        "Growing up means already knowing how things work", "Nobody actually taught me, and asking out loud feels like confessing",
        "'Adulting' is named as a joke; the private, shame-laden relearning of basics is not.",
        ["adulting", "lifelong learning"], ["sig-10", "sig-11", "sig-12", "sig-13"],
        7.0, 7.5,
        "'Adulting' turns this into a meme; the hidden-learning behaviour and its shame have no name.",
        "Very high shame, repeated private workarounds and a fiercely kind micro-community.",
        existing=[NamedTerm(term="adulting", closeness="A jokey umbrella term; doesn't touch the secrecy.")],
    )
    basics.skeleton = "A growth that can only happen if it is hidden from the people it would impress."
    basics.banned_obvious = ["imposter syndrome", "growth mindset", "never too late", "Khan Academy", "beginner's mind", "kaizen", "life hacks", "YouTube university", "adulting", "Dunning-Kruger"]
    basics.seed_domains = ["hermit crab shell-vacancy chains", "coppicing", "dry-stone walling", "seed dormancy and seed banks"]
    basics.latent = [
        LatentConcept(name="Vacancy chain", domain="hermit crab shell-vacancy chains", mechanism="When a larger empty shell appears, hermit crabs line up by size and swap shells in sequence, each moving into the shell just vacated by a slightly larger crab.",
                      structural_rhyme="Growth happens by inheriting what the person just ahead of you has outgrown, not by being taught from above.", obviousness=1.0, verified=True, source=_wiki("Vacancy chain", "Vacancy_chain")),
        LatentConcept(name="Coppicing", domain="coppicing", mechanism="Trees are cut back to a stump (a stool), which then sends up vigorous new shoots from established roots; woods are cut in rotation.",
                      structural_rhyme="Old roots with new growth: an adult starting over without starting from nothing.", obviousness=3.5, verified=True, source=_wiki("Coppicing", "Coppicing")),
    ]
    basics.collisions = [
        _card(basics, 1, "Vacancy chain", "Leave your old shell where the next one can find it.",
              "The best teacher for a secret beginner isn't an expert, it's someone who learned the same thing last month and still remembers what step 1 felt like. Build the queue, not the classroom.",
              "Shell swap = passing on a just-outgrown skill to the person one step behind; queuing by size = matching learners by how recently they learned.",
              ["shell swap", "one-step-ahead"], "Learning a basic from someone who only just learned it themselves, so nobody is the expert.",
              "A bank, supermarket or DIY brand hosts anonymous one-step-ahead swaps: you learn reading a payslip from someone who learned it last week.",
              "Could become a content farm that monetises people's embarrassment.", 9, 8, ["sig-10", "sig-12", "sig-13"]),
        _card(basics, 2, "Coppicing", "Cut it to the stool. The roots are already old.",
              "Starting over at 36 is not starting from nothing. It's coppicing: the new growth is fast because the roots are already deep.",
              "Stool = existing adult competence; new shoots = basics learned late but fast.",
              ["coppiced", "late shoots"], "Learning something basic late, quickly, because the rest of you is already grown.",
              "An education or tools brand that teaches basics as 'fast because you're grown', not 'remedial'.", "Could still frame not knowing as a deficit.", 7, 7.5, ["sig-10", "sig-11"]),
    ]
    basics.conscience = ConscienceBrief(
        gives="Relief, privacy and a way to learn without performing competence.",
        takes="Naming it publicly could expose the very people whose refuge is secrecy.",
        who_is_vulnerable="People with low literacy or numeracy, neurodivergent adults, people from care backgrounds.",
        exploitation_vectors=["Shame-based ads ('still can't boil an egg?')", "Upselling courses to people who just need one answer"],
        honest_version="Private by default, free at the point of the basic question, and never on-camera.",
        questions_for_operator=["Can this be done without anyone ever being shown not knowing?", "Who profits from the shame continuing?", "Is the brand a host or a teacher?"],
    )

    rot = _space("space-4", "Bed days", "I want permission to do nothing at all for a day.", "Rest", "Productivity guilt",
                 "It is named.", ["bed rotting"], ["sig-14"], 1.5, 8.5,
                 "'Bed rotting' is a named trend with mainstream explainers and brand activity.", "Real and widely felt.",
                 existing=[NamedTerm(term="bed rotting", closeness="Exact match.")], legible=True)
    keys = _space("space-5", "Key card keepers", "I want a trace of the places I passed through.", "Travel memory", "Nothing physical to keep",
                  "Too small to tell.", [], ["sig-15"], 8.0, 2.5, "No shared name.", "One low-weight signal; a hobby, not a need.")

    for s in (friends, pre, basics):
        s.shortlisted = True
    run = Run(id=run_id, status="done", stage="done", demo=True,
              config=RunConfig(focus="everyday life", brand=None, seed=7),
              signals=SIGNALS, spaces=[friends, basics, pre, rot, keys])
    run.spaces.sort(key=lambda s: s.scores.product, reverse=True)
    dig = {
        "space-1-c1": ["hefted flock Lake District shepherds", "r/AskUK standing weekly pub night friends", "how long until a habit feels like belonging", "Open question: what happens to a heft when one friend moves away?"],
        "space-1-c2": ["Shmita debt release meaning", "\"sorry I've been rubbish\" texting friends", "Open question: who gets to declare the jubilee?"],
        "space-1-c3": ["change ringing method explained", "friend group rotating host rituals"],
        "space-2-c1": ["bridge expansion joint how it works", "\"pre-tired\" plans", "Open question: is the gap the plan, or protection from it?"],
        "space-2-c2": ["annealing heat treatment explained", "soft yes calendar invites"],
        "space-3-c1": ["hermit crab vacancy chain research", "adults learning basic skills secretly", "r/NoStupidQuestions embarrassing adult basics", "Open question: does the chain break if anyone is watched?"],
        "space-3-c2": ["coppicing rotation woodland", "learning to swim as an adult"],
    }
    titles = {
        "space-1-c1": "The standing table", "space-1-c2": "The catch-up amnesty", "space-1-c3": "Friendship by rota",
        "space-2-c1": "Sell the gap", "space-2-c2": "Plans that set slowly",
        "space-3-c1": "Learn from one step ahead", "space-3-c2": "Late shoots, deep roots",
    }
    borrowed = {
        "Hefting": "Hill farmers' sheep learn where home is and stay there without fences, and the lambs learn it from their mothers.",
        "Shmita": "In Jewish tradition, every seventh year the fields rest and many debts are simply cancelled.",
        "Change ringing": "Church bell-ringers don't play tunes; they ring set patterns, and the music comes from the pattern.",
        "Expansion joint": "Bridges have deliberate gaps built in so they can stretch in the heat without cracking.",
        "Annealing": "Metalworkers heat metal and cool it slowly so it stops being brittle.",
        "Vacancy chain": "When a bigger shell turns up, hermit crabs queue by size and each moves into the one the next crab left.",
        "Coppicing": "Foresters cut trees back to the stump and they regrow fast, because the roots are already there.",
    }
    plain_fit = {
        "space-1-c1": "The reminder is the fence. Friendships that last are held by a place and a habit, the way the flock is held by the hill.",
        "space-1-c2": "Owed catch-ups pile up like debt until it's easier to let the friendship go. Cancelling the debt makes it easy to start again.",
        "space-1-c3": "An agreed rotation of who hosts does the work that willpower can't.",
        "space-2-c1": "The plan isn't the problem. It's the plan pressing on everything around it. A deliberate gap takes the strain.",
        "space-2-c2": "Plans that arrive too fast feel brittle. Ones that firm up gradually don't hang over you.",
        "space-3-c1": "The best teacher for an embarrassing basic is someone who only just learned it, not an expert.",
        "space-3-c2": "Starting over as an adult isn't starting from nothing. The rest of you is already grown.",
    }
    for sp in (friends, pre, basics):
        for c in sp.collisions:
            c.dig_deeper = dig.get(c.id, [])
            c.title = titles.get(c.id, "")
            c.borrowed_from = borrowed.get(c.latent_name, "")
            c.brand_fit = c.coherence
            c.bridge = plain_fit.get(c.id, c.bridge)
        sp.collisions.sort(key=lambda c: c.surprise)
    from .activity import AgentState
    t0 = 1_760_000_000.0
    trail = [
        ("Reddit scout", "scan", "", ["is it weird that I set reminders to text friends", "catch-up debt"]),
        ("TikTok scout", "scan", "", ["pre-tired tiktok", "not me learning to boil an egg at 30"]),
        ("YouTube scout", "scan", "", ["things nobody tells you about adult friendship"]),
        ("Clusterer", "cluster", "", []),
        ("Scorer · Scheduled intimacy", "score", "space-1", ["friendship recession trend", "scheduling friends reminders trend name"]),
        ("Scorer · Pre-tiredness", "score", "space-2", ["\"pre-tired\" meaning", "anticipatory exhaustion social plans"]),
        ("Scorer · Secret beginners", "score", "space-3", ["adulting trend", "adults secretly learning basic skills"]),
        ("Diver · Scheduled intimacy", "latent", "space-1", ["hefting sheep hefted flock", "Shmita sabbatical year debts", "change ringing method ringing"]),
        ("Diver · Pre-tiredness", "latent", "space-2", ["expansion joint bridges thermal", "annealing metal stress relief"]),
        ("Diver · Secret beginners", "latent", "space-3", ["hermit crab vacancy chain", "coppicing stool regrowth"]),
    ]
    agents = []
    for i, (label, stage, sid, qs) in enumerate(trail):
        start = t0 + i * 20
        agents.append(AgentState(id=f"a{i + 1}", label=label, stage=stage, space_id=sid, status="done", started_at=start,
                                 last_event_at=start + 70, ended_at=start + 70, searches=len(qs), queries=qs, sources=len(qs) * 9))
    run.agents = agents
    run.stats = {"sources": 0, "signals": len(SIGNALS), "ungrounded_dropped": 0, "spaces": 5, "shortlisted": 3,
                 "latent_verified": 7, "latent_rejected": 0, "cards": 7}
    return run
