from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class SimilarityEvidence:
    category: str
    description: str
    channel_a_post_ids: tuple[int, ...] = field(default_factory=tuple)
    channel_b_post_ids: tuple[int, ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class SimilarityResult:
    channel_a: str
    channel_b: str
    style_score: float
    narrative_score: float
    temporal_score: float
    structural_score: float
    overall_score: float
    confidence: float
    explanation: str
    alternative_explanations: tuple[str, ...]
    evidence: tuple[SimilarityEvidence, ...]
    methodology_version: str = "similarity-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
