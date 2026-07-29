from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.evidence.review import EvidenceGap
from app.workspaces.models import Workspace, WorkspaceItemType


class EvidenceRequestStatus(StrEnum):
    QUEUED = "queued"
    COLLECTING = "collecting"
    RETRY_WAIT = "retry_wait"
    LINKING = "linking"
    RESOLVED = "resolved"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True, frozen=True)
class SourcePlanItem:
    source_type: str
    source_id: str
    reason: str


@dataclass(slots=True, frozen=True)
class EvidenceRequestPlan:
    claim_id: str
    gap_codes: tuple[str, ...]
    query_terms: tuple[str, ...]
    sources: tuple[SourcePlanItem, ...]
    priority: str


def build_request_plan(
    workspace: Workspace,
    claim: dict[str, Any],
    gaps: tuple[EvidenceGap, ...],
) -> EvidenceRequestPlan:
    relevant = tuple(gap for gap in gaps if gap.claim_id == claim["claim_id"])
    if not relevant:
        raise ValueError("Для claim нет evidence gaps")
    words = re.findall(r"[\w.-]{4,}", f"{claim.get('statement', '')} {claim.get('assessment', '')}".casefold())
    stop = {"который", "которые", "количество", "увеличилось", "выявлены", "появились", "информационное"}
    terms = tuple(dict.fromkeys(word for word in words if word not in stop))[:12]
    sources: list[SourcePlanItem] = []
    for item in workspace.items:
        if item.item_type is WorkspaceItemType.CHANNEL:
            sources.append(SourcePlanItem("telegram", item.normalized_value, "workspace channel"))
        elif item.item_type is WorkspaceItemType.RSS:
            sources.append(SourcePlanItem("rss", item.normalized_value, "workspace rss"))
    priority = "high" if any(gap.severity == "high" for gap in relevant) else "normal"
    return EvidenceRequestPlan(
        claim_id=str(claim["claim_id"]),
        gap_codes=tuple(dict.fromkeys(gap.code for gap in relevant)),
        query_terms=terms,
        sources=tuple(sources),
        priority=priority,
    )
