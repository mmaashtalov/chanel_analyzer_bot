from pathlib import Path

import pytest

from app.evidence.contradictions import (
    ContradictionResolutionAction,
    ContradictionStatus,
    default_resolution_claim,
    resolution_history_integrity,
    stable_contradiction_id,
    triage_priority,
    validate_resolution,
)
from app.reports.contradiction_pdf import build_contradiction_exports


def test_action_aliases_and_status_mapping() -> None:
    assert ContradictionResolutionAction.parse("confirm") is ContradictionResolutionAction.CONFIRM_CONTRADICTION
    assert ContradictionResolutionAction.parse("newer") is ContradictionResolutionAction.ACCEPT_NEWER
    assert ContradictionStatus.parse("unresolved") is ContradictionStatus.OPEN


def test_stable_id_and_priority_are_deterministic() -> None:
    first = stable_contradiction_id("ws", "identity", "source", "target")
    second = stable_contradiction_id("ws", "identity", "source", "target")
    assert first == second
    assert triage_priority("critical", 0.8) > triage_priority("low", 0.99)


def test_newer_claim_must_be_explicit_and_later() -> None:
    validate_resolution(
        ContradictionResolutionAction.ACCEPT_NEWER,
        "source",
        "target",
        "target",
    )
    assert default_resolution_claim(
        "source", "target", "2026-07-28T00:00:00+00:00", "2026-07-29T00:00:00+00:00"
    ) == "target"
    with pytest.raises(ValueError):
        validate_resolution(
            ContradictionResolutionAction.MARK_COMPATIBLE,
            "source",
            "target",
            "target",
        )


def test_history_integrity_changes_when_event_is_appended() -> None:
    first = [{"event_hash": "a", "new_status": "confirmed"}]
    second = first + [{"event_hash": "b", "new_status": "compatible"}]
    assert resolution_history_integrity(first) != resolution_history_integrity(second)


def test_contradiction_exports_are_machine_and_human_readable(tmp_path: Path) -> None:
    report = {
        "workspace_id": "ws-demo",
        "status_filter": "all",
        "contradiction_count": 1,
        "unresolved_count": 1,
        "integrity_hash": "a" * 64,
        "contradictions": [{
            "contradiction_id": "ctr_demo",
            "severity": "high",
            "confidence": 0.8,
            "triage_priority": 0.9,
            "status": "open",
            "source_generated_at": "2026-07-28T00:00:00+00:00",
            "target_generated_at": "2026-07-29T00:00:00+00:00",
            "source_statement": "Первое утверждение",
            "target_statement": "Противоречащее утверждение",
            "rationale": ["semantic_direction_changed"],
            "history": [],
        }],
    }
    json_path, pdf_path = build_contradiction_exports(report, tmp_path)
    assert json_path.exists() and json_path.stat().st_size > 0
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
