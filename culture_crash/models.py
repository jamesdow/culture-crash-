"""Persistent data model for a Culture Crash run.

Everything the engine finds is stored here, along with the operator's
conscience verdicts. The engine itself never writes a verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field

from .activity import AgentState

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
    title: str = ""
    borrowed_from: str = ""  # the borrowed concept explained in one plain sentence
    brand_fit: float = 5.0
    cannes_echo: str = ""
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
    dig_deeper: list[str] = []  # follow-up searches and questions for whoever picks this up


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
    territory: str = ""
    brand_fit: float = 5.0
    right_to_play: str = ""
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
    near_miss: bool = False  # shortlisted although below the bar, so a run never ends with nothing
    picked: bool = False  # the operator chose to dive into it anyway
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
    always_show: bool = True  # if too few spaces clear the band, also dive into the closest near misses
    seeds_per_space: int = 4
    cards_per_space: int = 10  # ideas kept per space; the strategist prefers more ideas to fewer
    brand_core_share: float = 0.7  # share of scouting aimed at the brand's core territories
    seed: Optional[int] = None
    model: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"


class Territory(BaseModel):
    name: str
    why: str
    search_terms: list[str] = []
    core: bool = True


class BrandTerritory(BaseModel):
    brand: str
    summary: str
    territories: list[Territory] = []
    already_says: list[str] = []
    subreddits: list[str] = []

    def block(self) -> str:
        lines = [f"Brand: {self.brand}. {self.summary}"]
        for t in self.territories:
            lines.append(f"- {'CORE' if t.core else 'ADJACENT'}: {t.name}. {t.why}")
        if self.already_says:
            lines.append("Already says (avoid repeating): " + "; ".join(self.already_says))
        return "\n".join(lines)


class CachedResearch(BaseModel):
    """Search results are saved the moment they arrive, so a later step stalling never throws them away."""
    text: str
    sources: list[Source] = []
    cited_excerpts: list[tuple[str, str]] = []


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
    agents: list[AgentState] = []  # live view of each unit of work, for the progress panel
    research_cache: dict[str, CachedResearch] = {}
    territory: Optional[BrandTerritory] = None
    error: Optional[str] = None

    def signal(self, sid: str) -> Optional[Signal]:
        return next((s for s in self.signals if s.id == sid), None)

    def space(self, sid: str) -> Optional[Space]:
        return next((s for s in self.spaces if s.id == sid), None)
