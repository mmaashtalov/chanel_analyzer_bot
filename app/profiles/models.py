from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class IntelligenceProfile:
    username: str
    title: str
    subscribers: int | None
    collected_at: datetime
    source_post_count: int
    methodology_version: str
    style_vector: tuple[float, ...]
    temporal_vector: tuple[float, ...]
    structural_vector: tuple[float, ...]
    narrative_vector: tuple[float, ...]
    combined_vector: tuple[float, ...]
    metrics: dict[str, Any]
    content_dna: dict[str, Any]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["collected_at"] = self.collected_at.isoformat()
        return payload
