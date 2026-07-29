from __future__ import annotations

import hashlib
import json

from app.evolution.models import ChangeSeverity, EvolutionReport
from app.monitoring.models import AlertCandidate, AlertSeverity, SEVERITY_RANK


_SENSITIVITY_MINIMUM = {
    "low": AlertSeverity.LOW,
    "medium": AlertSeverity.MEDIUM,
    "high": AlertSeverity.HIGH,
    "critical": AlertSeverity.CRITICAL,
}


def severity_allowed(severity: AlertSeverity, sensitivity: str) -> bool:
    minimum = _SENSITIVITY_MINIMUM.get(sensitivity.casefold(), AlertSeverity.HIGH)
    return SEVERITY_RANK[severity] >= SEVERITY_RANK[minimum]


def _fingerprint(username: str, event) -> str:
    payload = {
        "username": username,
        "event_type": event.event_type,
        "category": event.category,
        "title": event.title,
        "new_value": event.new_value,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def alerts_from_evolution(report: EvolutionReport, sensitivity: str) -> tuple[AlertCandidate, ...]:
    severity_map = {
        ChangeSeverity.CRITICAL: AlertSeverity.CRITICAL,
        ChangeSeverity.HIGH: AlertSeverity.HIGH,
        ChangeSeverity.MEDIUM: AlertSeverity.MEDIUM,
        ChangeSeverity.LOW: AlertSeverity.LOW,
    }
    alerts: list[AlertCandidate] = []
    for event in report.events:
        severity = severity_map[event.severity]
        if not severity_allowed(severity, sensitivity):
            continue
        alerts.append(AlertCandidate(
            severity=severity,
            category=event.category,
            title=event.title,
            description=event.description,
            confidence=event.confidence,
            evidence=tuple(event.evidence),
            fingerprint=_fingerprint(report.username, event),
        ))
    return tuple(alerts)
