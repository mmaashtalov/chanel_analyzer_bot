from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AlertSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_RANK = {
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
    AlertSeverity.CRITICAL: 4,
}


@dataclass(slots=True, frozen=True)
class AlertCandidate:
    severity: AlertSeverity
    category: str
    title: str
    description: str
    confidence: float
    evidence: tuple[int, ...]
    fingerprint: str


@dataclass(slots=True, frozen=True)
class WatchSummary:
    id: str
    channel_username: str
    sensitivity: str
    interval_minutes: int
    enabled: bool
    next_check_at: datetime
    last_checked_at: datetime | None
    consecutive_failures: int
