from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class WorkspaceTrend(StrEnum):
    STABLE = "stable"
    GROWING = "growing"
    DECLINING = "declining"
    ESCALATING = "escalating"
    FRAGMENTING = "fragmenting"
    EMERGING_NARRATIVE = "emerging_narrative"
    MAJOR_SHIFT = "major_shift"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(slots=True, frozen=True)
class EvolutionObservation:
    category: str
    severity: str
    observation: str
    evidence: tuple[str, ...]
    confidence: float
    assessment: str


@dataclass(slots=True, frozen=True)
class WorkspaceEvolutionReport:
    workspace_id: str
    workspace_name: str
    baseline_snapshot_id: str
    current_snapshot_id: str
    baseline_generated_at: datetime
    current_generated_at: datetime
    trend: WorkspaceTrend
    confidence: float
    metric_deltas: dict[str, float | int | None]
    added_entities: tuple[tuple[str, int], ...]
    removed_entities: tuple[tuple[str, int], ...]
    added_domains: tuple[tuple[str, int], ...]
    removed_domains: tuple[tuple[str, int], ...]
    added_keywords: tuple[tuple[str, int], ...]
    removed_keywords: tuple[tuple[str, int], ...]
    alert_delta: dict[str, int]
    observations: tuple[EvolutionObservation, ...]
    limitations: tuple[str, ...]
    methodology_version: str = "workspace-evolution-v1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trend"] = self.trend.value
        payload["baseline_generated_at"] = self.baseline_generated_at.isoformat()
        payload["current_generated_at"] = self.current_generated_at.isoformat()
        return payload
