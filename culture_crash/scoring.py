"""The maths. Rank by product, not sum, so a space has to clear both bars."""

from __future__ import annotations

from statistics import mean
from urllib.parse import urlparse

from .models import Quadrant, Signal


def clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, float(x)))


def need_features(signals: list[Signal]) -> tuple[float, dict[str, float]]:
    """Evidence-side need score (0-10) computed from the signals themselves,
    so the model's judgment is checked against something it can't talk up."""
    if not signals:
        return 0.0, {}
    domains = {urlparse(s.source.url).netloc.removeprefix("www.") or s.source.url for s in signals}
    parts = {
        "volume": min(len(signals) / 6, 1.0),
        "kind_diversity": len({s.kind for s in signals}) / 5,
        "shame_present": 1.0 if any(s.kind == "shame" for s in signals) else 0.0,
        "emotional_weight": mean(s.emotional_weight for s in signals) / 5,
        "source_spread": min(len(domains) / 4, 1.0),
    }
    weights = {"volume": 0.25, "kind_diversity": 0.2, "shame_present": 0.15, "emotional_weight": 0.25, "source_spread": 0.15}
    score = 10 * sum(parts[k] * weights[k] for k in parts)
    return round(score, 2), {k: round(v, 2) for k, v in parts.items()}


def blend_need(model_need: float, feature_need: float) -> float:
    return round(0.6 * clamp(model_need) + 0.4 * clamp(feature_need), 2)


def product(distance: float, need: float) -> float:
    return round(clamp(distance) * clamp(need), 2)


def quadrant(distance: float, need: float, band: float) -> Quadrant:
    hi_d, hi_n = distance >= band, need >= band
    if hi_d and hi_n:
        return "target"
    if hi_n:
        return "already_mined"
    if hi_d:
        return "curiosity"
    return "noise"


DISCARD_REASONS = {
    "already_mined": "Real need, but the culture already has language for it, so the value exchange is thin.",
    "curiosity": "Far from the named vocabulary, but not enough felt need underneath it yet.",
    "noise": "Neither unnamed nor load-bearing.",
}


def mad_factor(surprise: float, coherence: float) -> float:
    """Geometric, like the space score: a wild card that doesn't land is worth little."""
    return round(clamp(surprise) * clamp(coherence) / 10, 2)
