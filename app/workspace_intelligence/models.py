from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"


@dataclass(slots=True, frozen=True)
class ChannelIntelligence:
    username: str
    profile_version: int
    posts_count: int
    confidence: float
    mean_views: float | None = None
    engagement_per_1000: float | None = None
    posts_per_day: float | None = None
    top_terms: tuple[str, ...] = ()
    entities_count: int = 0
    domains_count: int = 0
    latest_collected_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class WorkspaceAlertFact:
    channel_username: str
    severity: str
    title: str
    confidence: float
    created_at: datetime


@dataclass(slots=True, frozen=True)
class WorkspaceIntelligenceInput:
    workspace_id: str
    workspace_name: str
    requested_channels: tuple[str, ...]
    channels: tuple[ChannelIntelligence, ...] = ()
    entity_mentions: dict[str, int] = field(default_factory=dict)
    domain_mentions: dict[str, int] = field(default_factory=dict)
    keyword_mentions: dict[str, int] = field(default_factory=dict)
    alerts: tuple[WorkspaceAlertFact, ...] = ()
    generated_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class WorkspaceFinding:
    category: str
    severity: str
    title: str
    description: str
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class WorkspaceIntelligenceReport:
    workspace_id: str
    workspace_name: str
    generated_at: datetime
    coverage_status: CoverageStatus
    coverage_ratio: float
    requested_channel_count: int
    analyzed_channel_count: int
    total_posts: int
    weighted_confidence: float
    mean_views: float | None
    mean_engagement_per_1000: float | None
    mean_posts_per_day: float | None
    top_entities: tuple[tuple[str, int], ...]
    top_domains: tuple[tuple[str, int], ...]
    top_keywords: tuple[tuple[str, int], ...]
    alert_counts: dict[str, int]
    channels: tuple[ChannelIntelligence, ...]
    findings: tuple[WorkspaceFinding, ...]
    limitations: tuple[str, ...]
    methodology_version: str = "workspace-intelligence-v1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage_status"] = self.coverage_status.value
        payload["generated_at"] = self.generated_at.isoformat()
        for channel in payload["channels"]:
            if channel["latest_collected_at"] is not None:
                channel["latest_collected_at"] = channel["latest_collected_at"].isoformat()
        return payload
