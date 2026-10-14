"""Persistent data model for a Culture Crash run.

Everything the engine finds is stored here, along with the operator's
conscience verdicts. The engine itself never writes a verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field

SignalKind = Literal["slang", "workaround", "micro_community", "shame", "friction"]
SIGNAL_KINDS: tuple[SignalKind, ...] = ("slang", "workaround", "micro_community", "shame", "friction")

Quadrant = Literal["target", "already_mined", "curiosity", "noise"]
VerdictStatus = Literal["pending", "gives", "takes", "unsure"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Source(BaseModel):
    """A page the engine actually retrieved (from web search or Reddit)."""

    url: str
    title: str = ""
    date: Optional[str] = None
    origin: str = "web"  # the route that retrieved it: web-search, reddit-rss, yt-dlp, apify-tiktok, demo...

    @computed_field  # type: ignore[prop-decorator]
    @property
    def platform(self) -> str:
        from .harvest import platform_of

        if self.origin == "demo":  # illustrative signals carry their platform in the title
            t = self.title.lower()
            return next((p for p in ("reddit", "tiktok", "instagram", "youtube") if p in t), "web")
        return platform_of(self.url)


class Signal(BaseModel):
    id: str
    kind: SignalKind
    observation: str
    verbatim: str = ""
    emotional_weight: int = Field(3, ge=1, le=5)
    source: Source


class NamedTerm(BaseModel):
    term: str
    closeness: str = ""
    source: Optional[Source] = None


class Scores(BaseModel):
    cultural_distance: float
    distance_rationale: str
    existing_names: list[NamedTerm] = []
    legible_trend: bool = False
    need_model: float
    need_features: float
    need_intensity: float
    need_rationale: str
    feature_breakdown: dict[str, float] = {}
    product: float


class LatentConcept(BaseModel):
    name: str
    domain: str
    from_seed: bool = True
    mechanism: str
    structural_rhyme: str
    obviousness: float
    verified: bool = False
    source: Optional[Source] = None
    note: str = ""


class Collision(BaseModel):
    id: str
    latent_name: str
    oblique_strategy: str
    mad_thought: str
    bridge: str
    coinage: list[str] = []
    coinage_gloss: str = ""
    value_exchange: str
    risk_note: str
    surprise: float
    coherence: float
    mad_factor: float
    signal_ids: list[str] = []


class ConscienceBrief(BaseModel):
    gives: str
    takes: str
    who_is_vulnerable: str
    exploitation_vectors: list[str] = []
    honest_version: str
    questions_for_operator: list[str] = []


class Verdict(BaseModel):
    status: VerdictStatus = "pending"
    note: str = ""
    by: str = ""
    at: Optional[str] = None


class Space(BaseModel):
    id: str
    working_name: str
    unnamed_need: str
    pull_a: str
    pull_b: str
    why_unnamed: str
    nearest_named: list[str] = []
    signal_ids: list[str] = []
    scores: Optional[Scores] = None
    quadrant: Optional[Quadrant] = None
    shortlisted: bool = False
    discard_reason: str = ""
    skeleton: str = ""
    banned_obvious: list[str] = []
    seed_domains: list[str] = []
    latent: list[LatentConcept] = []
    collisions: list[Collision] = []
    conscience: Optional[ConscienceBrief] = None
    verdict: Verdict = Verdict()


class RunConfig(BaseModel):
    focus: Optional[str] = None
    brand: Optional[str] = None
    market: str = "UK and US"
    recency_days: int = 90
    platforms: list[Literal["web", "reddit", "tiktok", "instagram", "youtube"]] = ["web", "reddit", "tiktok", "instagram", "youtube"]
    subreddits: list[str] = []
    max_spaces: int = 8
    shortlist: int = 4
    band: float = 5.5
    seeds_per_space: int = 4
    cards_per_space: int = 3
    seed: Optional[int] = None
    model: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"


class ProgressEvent(BaseModel):
    at: str
    stage: str
    message: str


class Run(BaseModel):
    id: str
    created_at: str = Field(default_factory=now_iso)
    status: Literal["queued", "running", "done", "error"] = "queued"
    stage: str = "queued"
    demo: bool = False
    config: RunConfig = RunConfig()
    progress: list[ProgressEvent] = []
    sources: list[Source] = []
    signals: list[Signal] = []
    spaces: list[Space] = []
    stats: dict[str, int] = {}
    routes: dict[str, str] = {}  # platform -> how it was reached this run
    error: Optional[str] = None

    def signal(self, sid: str) -> Optional[Signal]:
        return next((s for s in self.signals if s.id == sid), None)

    def space(self, sid: str) -> Optional[Space]:
        return next((s for s in self.spaces if s.id == sid), None)
