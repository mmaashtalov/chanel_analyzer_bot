from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Iterable

from app.profiles.models import IntelligenceProfile


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    left, right = tuple(a), tuple(b)
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(x * y for x, y in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(x * x for x in left))
    norm_right = math.sqrt(sum(y * y for y in right))
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return _clamp(dot / (norm_left * norm_right))


@dataclass(slots=True, frozen=True)
class SimilarProfileCandidate:
    username: str
    title: str
    version: int
    style_score: float
    narrative_score: float
    temporal_score: float
    structural_score: float
    overall_score: float
    confidence: float
    classification: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ProfileSearchResult:
    source_username: str
    source_version: int
    candidates: tuple[SimilarProfileCandidate, ...]
    methodology_version: str = "profile-search-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_username": self.source_username,
            "source_version": self.source_version,
            "methodology_version": self.methodology_version,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def classify_similarity(score: float) -> str:
    if score >= 0.95:
        return "Практически идентичные профили"
    if score >= 0.85:
        return "Очень похожие профили"
    if score >= 0.70:
        return "Похожий публикационный профиль"
    if score >= 0.50:
        return "Частичные совпадения"
    return "Значимых совпадений мало"


def score_profiles(source: IntelligenceProfile, candidate: IntelligenceProfile, version: int) -> SimilarProfileCandidate:
    style = cosine_similarity(source.style_vector, candidate.style_vector)
    narrative = cosine_similarity(source.narrative_vector, candidate.narrative_vector)
    temporal = cosine_similarity(source.temporal_vector, candidate.temporal_vector)
    structural = cosine_similarity(source.structural_vector, candidate.structural_vector)

    # Theme alone must not dominate the result. Style and structure are the stronger signals.
    overall = 0.35 * style + 0.20 * narrative + 0.20 * temporal + 0.25 * structural
    non_narrative = (style + temporal + structural) / 3
    if narrative >= 0.85 and non_narrative < 0.45:
        overall = min(overall, 0.49)
    if max(style, temporal, structural) < 0.40:
        overall = min(overall, 0.44)

    confidence = _clamp(
        0.50 * min(source.confidence, candidate.confidence)
        + 0.25 * min(source.source_post_count, candidate.source_post_count) / 120
        + 0.25 * min(style, structural)
    )
    strongest = sorted(
        (("стиль", style), ("тематика", narrative), ("время", temporal), ("структура", structural)),
        key=lambda item: item[1],
        reverse=True,
    )[:2]
    explanation = (
        f"Главные совпадения: {strongest[0][0]} {strongest[0][1]:.0%} и "
        f"{strongest[1][0]} {strongest[1][1]:.0%}. "
        "Оценка описывает сходство профилей, а не доказывает общего автора."
    )
    return SimilarProfileCandidate(
        username=candidate.username,
        title=candidate.title,
        version=version,
        style_score=round(style, 4),
        narrative_score=round(narrative, 4),
        temporal_score=round(temporal, 4),
        structural_score=round(structural, 4),
        overall_score=round(_clamp(overall), 4),
        confidence=round(confidence, 4),
        classification=classify_similarity(overall),
        explanation=explanation,
    )
