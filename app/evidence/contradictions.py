from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ContradictionStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    COMPATIBLE = "compatible"
    RESOLVED_BY_NEWER = "resolved_by_newer"
    NEEDS_EVIDENCE = "needs_evidence"

    @classmethod
    def parse(cls, raw: str) -> ContradictionStatus:
        normalized = raw.strip().casefold()
        aliases = {
            "unresolved": cls.OPEN,
            "pending": cls.OPEN,
            "resolved": cls.RESOLVED_BY_NEWER,
            "newer": cls.RESOLVED_BY_NEWER,
            "evidence": cls.NEEDS_EVIDENCE,
        }
        return aliases[normalized] if normalized in aliases else cls(normalized)


class ContradictionResolutionAction(StrEnum):
    CONFIRM_CONTRADICTION = "confirm_contradiction"
    MARK_COMPATIBLE = "mark_compatible"
    ACCEPT_NEWER = "accept_newer"
    REQUEST_EVIDENCE = "request_evidence"

    @classmethod
    def parse(cls, raw: str) -> ContradictionResolutionAction:
        normalized = raw.strip().casefold().replace("-", "_")
        aliases = {
            "confirm": cls.CONFIRM_CONTRADICTION,
            "contradiction": cls.CONFIRM_CONTRADICTION,
            "confirmed": cls.CONFIRM_CONTRADICTION,
            "compatible": cls.MARK_COMPATIBLE,
            "compat": cls.MARK_COMPATIBLE,
            "newer": cls.ACCEPT_NEWER,
            "resolve_newer": cls.ACCEPT_NEWER,
            "accept_newer": cls.ACCEPT_NEWER,
            "evidence": cls.REQUEST_EVIDENCE,
            "request_evidence": cls.REQUEST_EVIDENCE,
            "needs_evidence": cls.REQUEST_EVIDENCE,
        }
        return aliases[normalized] if normalized in aliases else cls(normalized)


ACTION_STATUS: dict[ContradictionResolutionAction, ContradictionStatus] = {
    ContradictionResolutionAction.CONFIRM_CONTRADICTION: ContradictionStatus.CONFIRMED,
    ContradictionResolutionAction.MARK_COMPATIBLE: ContradictionStatus.COMPATIBLE,
    ContradictionResolutionAction.ACCEPT_NEWER: ContradictionStatus.RESOLVED_BY_NEWER,
    ContradictionResolutionAction.REQUEST_EVIDENCE: ContradictionStatus.NEEDS_EVIDENCE,
}

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def normalize_severity(value: str | None) -> str:
    normalized = str(value or "medium").strip().casefold()
    return normalized if normalized in _SEVERITY_RANK else "medium"


def severity_rank(value: str | None) -> int:
    return _SEVERITY_RANK[normalize_severity(value)]


def triage_priority(severity: str | None, confidence: float) -> float:
    """Return a bounded score used to order the phone triage queue."""

    bounded_confidence = max(0.0, min(1.0, float(confidence)))
    return round((severity_rank(severity) / 4) * 0.7 + bounded_confidence * 0.3, 6)


def stable_contradiction_id(
    workspace_id: str,
    claim_identity_id: str,
    source_claim_id: str,
    target_claim_id: str,
) -> str:
    raw = f"{workspace_id}|{claim_identity_id}|{source_claim_id}|{target_claim_id}"
    return "ctr_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def validate_resolution(
    action: ContradictionResolutionAction,
    source_claim_id: str,
    target_claim_id: str,
    selected_claim_id: str | None,
) -> None:
    if action is ContradictionResolutionAction.ACCEPT_NEWER:
        if selected_claim_id not in {source_claim_id, target_claim_id}:
            raise ValueError("Для action newer укажите source или target claim этой связи")
        return
    if selected_claim_id is not None:
        raise ValueError("Выбор claim разрешён только для action newer")


def default_resolution_claim(
    source_claim_id: str,
    target_claim_id: str,
    source_generated_at: str,
    target_generated_at: str,
) -> str:
    if target_generated_at > source_generated_at:
        return target_claim_id
    if source_generated_at > target_generated_at:
        return source_claim_id
    raise ValueError("Нельзя выбрать newer claim: даты наблюдений совпадают")


def event_hash(
    *,
    contradiction_id: str,
    telegram_user_id: int,
    previous_status: str | None,
    action: str,
    new_status: str,
    selected_claim_id: str | None,
    comment: str | None,
    previous_event_hash: str | None,
    created_at: str,
) -> str:
    payload = "|".join(
        (
            contradiction_id,
            str(telegram_user_id),
            previous_status or "",
            action,
            new_status,
            selected_claim_id or "",
            comment or "",
            previous_event_hash or "",
            created_at,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolution_history_integrity(events: Iterable[dict]) -> str:
    payload = "|".join(
        f"{item.get('event_hash', '')}>{item.get('new_status', '')}"
        for item in events
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContradictionDecision:
    action: ContradictionResolutionAction
    selected_claim_id: str | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        if self.comment is not None and len(self.comment) > 2000:
            raise ValueError("Комментарий не должен превышать 2000 символов")
