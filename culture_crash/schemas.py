"""Shapes Claude must answer in for each structured stage.

Numbers are kept unconstrained here and clamped in code, so the schemas stay
inside what structured outputs accept.
"""

from __future__ import annotations

from pydantic import BaseModel

from .models import ConscienceBrief, SignalKind


class ExtractedSignal(BaseModel):
    kind: SignalKind
    observation: str
    verbatim: str
    emotional_weight: int
    source_ref: str


class SignalExtraction(BaseModel):
    signals: list[ExtractedSignal]


class ClusterSpace(BaseModel):
    working_name: str
    unnamed_need: str
    pull_a: str
    pull_b: str
    why_unnamed: str
    nearest_named: list[str]
    signal_ids: list[str]


class ClusterResult(BaseModel):
    spaces: list[ClusterSpace]


class ExistingName(BaseModel):
    term: str
    closeness: str
    source_ref: str


class ScoreResult(BaseModel):
    existing_names: list[ExistingName]
    legible_trend: bool
    cultural_distance: float
    distance_rationale: str
    need_intensity: float
    need_rationale: str


class LatentCandidate(BaseModel):
    name: str
    domain: str
    from_seed: bool
    mechanism: str
    structural_rhyme: str
    obviousness: float


class LatentDive(BaseModel):
    skeleton: str
    first_thoughts: list[str]
    candidates: list[LatentCandidate]


class LatentCheck(BaseModel):
    name: str
    verified: bool
    source_ref: str
    corrected_mechanism: str
    note: str


class LatentVerification(BaseModel):
    checks: list[LatentCheck]


class CollisionCard(BaseModel):
    latent_name: str
    oblique_strategy: str
    mad_thought: str
    bridge: str
    coinage: list[str]
    coinage_gloss: str
    value_exchange: str
    risk_note: str
    surprise: float
    coherence: float
    signal_ids: list[str]
    dig_deeper: list[str]


class CollisionSet(BaseModel):
    cards: list[CollisionCard]


ConscienceOut = ConscienceBrief
