"""End-to-end pipeline test with a scripted stand-in for Claude."""

from __future__ import annotations

from fastapi.testclient import TestClient

from culture_crash import scoring
from culture_crash.llm import Research
from culture_crash.models import Run, RunConfig, Source
from culture_crash.pipeline import Engine
from culture_crash.harvest import Post, Unavailable
from culture_crash.report import render
from culture_crash.schemas import (
    ClusterResult, ClusterSpace, CollisionCard, CollisionSet, ConscienceOut, ExistingName, ExtractedSignal,
    LatentCandidate, LatentCheck, LatentDive, LatentVerification, ScoreResult, SignalExtraction,
)
from culture_crash.server import create_app
from culture_crash.store import RunStore


class FakeLLM:
    def __init__(self):
        self.calls: list[str] = []
        self.domains: list[list[str] | None] = []

    def research(self, system, prompt, max_searches=6, allowed_domains=None):
        self.calls.append("research")
        self.domains.append(allowed_domains)
        if allowed_domains == ["tiktok.com"]:
            return Research(text="notes", sources=[Source(url="https://www.tiktok.com/@a/video/1", title="T1"),
                                                   Source(url="https://www.tiktok.com/@b/video/2", title="T2")])
        return Research(text="notes", sources=[Source(url="https://forum.example/a", title="A"),
                                               Source(url="https://reddit.com/r/x/b", title="B")])

    def structured(self, system, prompt, schema, effort=None):
        self.calls.append(schema.__name__)
        if schema is SignalExtraction:
            return SignalExtraction(signals=[
                ExtractedSignal(kind="shame", observation="hides it", verbatim="don't judge me", emotional_weight=5, source_ref="S1"),
                ExtractedSignal(kind="workaround", observation="janky system", verbatim="", emotional_weight=4, source_ref="S2"),
                ExtractedSignal(kind="slang", observation="invented URL", verbatim="", emotional_weight=3, source_ref="S99"),
            ])
        if schema is ClusterResult:
            return ClusterResult(spaces=[
                ClusterSpace(working_name="Hot space", unnamed_need="need", pull_a="a", pull_b="b", why_unnamed="w",
                             nearest_named=[], signal_ids=["sig-01", "sig-02", "sig-404"]),
                ClusterSpace(working_name="Named already", unnamed_need="need2", pull_a="a", pull_b="b", why_unnamed="w",
                             nearest_named=["x"], signal_ids=["sig-01"]),
            ])
        if schema is ScoreResult:
            named = "Named already" in prompt
            return ScoreResult(existing_names=[ExistingName(term="x", closeness="exact", source_ref="S1")],
                               legible_trend=named, cultural_distance=9 if not named else 8,
                               distance_rationale="r", need_intensity=9, need_rationale="n")
        if schema is LatentDive:
            return LatentDive(skeleton="s", first_thoughts=["Obvious Thing"], candidates=[
                LatentCandidate(name="Obvious Thing", domain="d", from_seed=True, mechanism="m", structural_rhyme="r", obviousness=0),
                LatentCandidate(name="Hefting", domain="grazing", from_seed=True, mechanism="m", structural_rhyme="r", obviousness=1),
                LatentCandidate(name="Made Up", domain="d", from_seed=True, mechanism="m", structural_rhyme="r", obviousness=2),
                LatentCandidate(name="Wild", domain="any", from_seed=False, mechanism="m", structural_rhyme="r", obviousness=3),
            ])
        if schema is LatentVerification:
            return LatentVerification(checks=[
                LatentCheck(name="Hefting", verified=True, source_ref="S1", corrected_mechanism="fixed", note=""),
                LatentCheck(name="Made Up", verified=True, source_ref="", corrected_mechanism="", note="no source"),
                LatentCheck(name="Wild", verified=False, source_ref="S2", corrected_mechanism="", note="not real"),
            ])
        if schema is CollisionSet:
            return CollisionSet(cards=[
                CollisionCard(latent_name="Hefting", oblique_strategy="Graze the same hill.", mad_thought="m", bridge="b",
                              coinage=["hefted"], coinage_gloss="g", value_exchange="v", risk_note="r",
                              surprise=8, coherence=9, signal_ids=["sig-01", "sig-77"]),
                CollisionCard(latent_name="Hefting", oblique_strategy="Weak card.", mad_thought="m", bridge="b",
                              coinage=[], coinage_gloss="", value_exchange="v", risk_note="r",
                              surprise=10, coherence=1, signal_ids=[]),
            ])
        if schema is ConscienceOut:
            return ConscienceOut(gives="g", takes="t", who_is_vulnerable="w", exploitation_vectors=["e"],
                                 honest_version="h", questions_for_operator=["q"])
        raise AssertionError(schema)


class Route:
    def __init__(self, name, posts=None, fail=False):
        self.name, self.posts, self.fail = name, posts or [], fail

    def ready(self):
        return True

    def harvest(self, spec):
        if self.fail:
            raise Unavailable("HTTP 403")
        return self.posts


def reddit_posts(n):
    return [Post(platform="reddit", url=f"https://www.reddit.com/r/AskUK/comments/{i}", title=f"Is it weird that I do thing number {i}",
                 text="long enough body text here", context="r/AskUK", engagement=i) for i in range(n)]


def fake_routes(platform):
    return {
        "reddit": [Route("reddit-json", fail=True), Route("reddit-rss", reddit_posts(10))],
        "tiktok": [Route("apify-tiktok", fail=True)],
        "instagram": [],
        "youtube": [Route("yt-dlp", [Post(platform="youtube", url="https://www.youtube.com/watch?v=x&lc=1",
                                          text="I didn't know there was a word for this", context="comment on: v")] * 3)],
    }[platform]


def test_full_pipeline(tmp_path):
    store = RunStore(tmp_path)
    llm = FakeLLM()
    run = Run(id="20260101-000000-abcd", config=RunConfig(seed=1, shortlist=2, cards_per_space=1))
    Engine(llm, store, routes=fake_routes).run(run)

    assert run.status == "done", run.error
    # Ungrounded signals (S99) are dropped and duplicates collapsed.
    assert all(s.source.url.startswith("https://") for s in run.signals)
    assert run.stats["ungrounded_dropped"] >= 6
    hot = next(s for s in run.spaces if s.working_name == "Hot space")
    named = next(s for s in run.spaces if s.working_name == "Named already")
    # Unknown signal ids are stripped from clusters.
    assert "sig-404" not in hot.signal_ids
    # Legible trends are capped and discarded; the hot space is shortlisted.
    assert named.scores.legible_trend and named.scores.cultural_distance <= 3 and not named.shortlisted
    assert hot.shortlisted and hot.quadrant == "target"
    # Obvious candidates are banned; only source-backed concepts count as verified.
    names = {c.name: c for c in hot.latent}
    assert "Obvious Thing" not in names
    assert names["Hefting"].verified and names["Hefting"].mechanism == "fixed"
    assert not names["Made Up"].verified and not names["Wild"].verified
    # Cards ranked by mad factor (product), invalid signal ids filtered.
    assert [c.oblique_strategy for c in hot.collisions] == ["Graze the same hill."]
    assert hot.collisions[0].signal_ids == ["sig-01"]
    # The engine never sets a verdict.
    assert all(s.verdict.status == "pending" for s in run.spaces)
    # Each platform records how it was reached; blocked ones fall back to domain-restricted search.
    assert run.routes["reddit"] == "reddit-rss"
    assert run.routes["youtube"] == "yt-dlp"  # fewer posts than wanted, but the best available
    assert run.routes["tiktok"] == "web search on tiktok.com"
    assert run.routes["instagram"] == "web search on instagram.com"
    assert ["tiktok.com"] in llm.domains and ["instagram.com"] in llm.domains
    platforms = {s.source.platform for s in run.signals}
    assert {"reddit", "tiktok", "youtube"} <= platforms
    assert run.stats["signals_tiktok"] >= 1

    md = render(run)
    assert "Graze the same hill." in md and "PENDING" in md
    brief = render(run, brief_only=True)
    assert "Graze the same hill." not in brief

    store.set_verdict(run.id, hot.id, "gives", "it gives permission", "tester")
    assert "Graze the same hill." in render(store.load(run.id), brief_only=True)


def test_scoring_product_needs_both_bars():
    assert scoring.product(10, 1) < scoring.product(5, 5)
    assert scoring.quadrant(8, 8, 5.5) == "target"
    assert scoring.quadrant(2, 8, 5.5) == "already_mined"
    assert scoring.quadrant(8, 2, 5.5) == "curiosity"
    assert scoring.mad_factor(10, 1) < scoring.mad_factor(6, 6)


def test_server_demo_and_verdict(tmp_path):
    c = TestClient(create_app(str(tmp_path)))
    rid = c.post("/api/demo").json()["id"]
    run = c.get(f"/api/runs/{rid}").json()
    sid = next(s["id"] for s in run["spaces"] if s["shortlisted"])
    assert c.post(f"/api/runs/{rid}/spaces/{sid}/verdict", json={"status": "takes", "note": "n"}).status_code == 200
    assert c.get(f"/api/runs/{rid}").json()["spaces"][0]["verdict"]["status"] in {"takes", "pending"}
    assert "DEMO DATA" in c.get(f"/api/runs/{rid}/export.md").text
    assert c.get("/api/runs/../../etc").status_code == 404
    assert c.get("/").status_code == 200


def test_resume_continues_after_failure(tmp_path):
    store = RunStore(tmp_path)

    class FlakyCluster(FakeLLM):
        fail = True

        def structured(self, system, prompt, schema, effort=None):
            if schema is ClusterResult and self.fail:
                self.fail = False
                raise TimeoutError("The read operation timed out")
            return super().structured(system, prompt, schema, effort)

    llm = FlakyCluster()
    run = Run(id="20260101-000000-beef", config=RunConfig(seed=1, shortlist=1, cards_per_space=1, platforms=["web"]))
    Engine(llm, store, routes=fake_routes).run(run)
    assert run.status == "error" and "timed out" in run.error and run.signals and not run.spaces

    scans_before = llm.calls.count("research")
    run = store.load(run.id)
    Engine(llm, store, routes=fake_routes).run(run)
    assert run.status == "done", run.error
    assert any(p.stage == "resume" for p in run.progress)
    hot = next(s for s in run.spaces if s.shortlisted)
    assert hot.collisions and hot.conscience
    # Scan was not repeated: only scoring and verification searches ran on resume.
    resumed_research = llm.calls.count("research") - scans_before
    assert resumed_research == len(run.spaces) + 1
