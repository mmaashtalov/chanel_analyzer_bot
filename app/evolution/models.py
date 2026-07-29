from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ChangeSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(slots=True, frozen=True)
class EvolutionEvent:
    event_type: str
    category: str
    title: str
    description: str
    severity: ChangeSeverity
    confidence: float
    old_value: Any
    new_value: Any
    delta: float | None = None
    evidence: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        payload["evidence"] = list(self.evidence)
        return payload


@dataclass(slots=True, frozen=True)
class EvolutionReport:
    username: str
    from_version: int
    to_version: int
    confidence: float
    events: tuple[EvolutionEvent, ...]
    executive_summary: tuple[str, ...]
    methodology_version: str = "evolution-v1"

    @property
    def highest_severity(self) -> ChangeSeverity | None:
        order = {
            ChangeSeverity.CRITICAL: 4,
            ChangeSeverity.HIGH: 3,
            ChangeSeverity.MEDIUM: 2,
            ChangeSeverity.LOW: 1,
        }
        return max((event.severity for event in self.events), key=order.get, default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "confidence": self.confidence,
            "events": [event.to_dict() for event in self.events],
            "executive_summary": list(self.executive_summary),
            "methodology_version": self.methodology_version,
        }
