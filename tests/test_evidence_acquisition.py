from datetime import UTC, datetime

import pytest

from app.evidence.acquisition import EvidenceRequestStatus, build_request_plan
from app.evidence.review import EvidenceGap
from app.workspaces.models import Workspace, WorkspaceItem, WorkspaceItemType


def workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        "ws-1", 42, "Demo", None, True,
        (
            WorkspaceItem("i1", WorkspaceItemType.CHANNEL, "@demo", "demo", None, {}, now),
            WorkspaceItem("i2", WorkspaceItemType.RSS, "https://example.org/rss", "https://example.org/rss", None, {}, now),
        ),
        now, now,
    )


def test_build_request_plan_uses_workspace_sources_and_gap_priority():
    claim = {"claim_id": "claim-1", "statement": "Ростех сообщил о новом этапе испытаний", "assessment": "Нужна проверка"}
    gaps = (EvidenceGap("claim-1", "entities", "no_primary_document", "high", "Нет документа"),)
    plan = build_request_plan(workspace(), claim, gaps)
    assert plan.priority == "high"
    assert plan.gap_codes == ("no_primary_document",)
    assert {item.source_type for item in plan.sources} == {"telegram", "rss"}
    assert "ростех" in plan.query_terms


def test_build_request_plan_rejects_claim_without_gap():
    with pytest.raises(ValueError):
        build_request_plan(workspace(), {"claim_id": "claim-1", "statement": "x"}, ())


def test_request_statuses_are_stable_api_values():
    assert EvidenceRequestStatus.QUEUED.value == "queued"
    assert EvidenceRequestStatus.RESOLVED.value == "resolved"
