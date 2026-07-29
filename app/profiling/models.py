from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class Evidence:
    message_id: int
    excerpt: str
    url: str | None = None


@dataclass(slots=True, frozen=True)
class Trait:
    name: str
    score: float
    confidence: float
    explanation: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class ContentDNAProfile:
    language_hint: str
    sample_size: int
    source_post_count: int
    lexical_diversity: float
    mean_sentence_length: float
    mean_paragraphs: float
    uppercase_ratio: float
    emoji_rate: float
    question_rate: float
    exclamation_rate: float
    ellipsis_rate: float
    dash_rate: float
    link_rate: float
    direct_address_rate: float
    dominant_markers: tuple[str, ...]
    repeated_phrases: tuple[tuple[str, int], ...]
    traits: tuple[Trait, ...]
    confidence: float
    limitations: tuple[str, ...]
    methodology_version: str = "content-dna-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
