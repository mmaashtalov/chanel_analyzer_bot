from app.evolution.models import ChangeSeverity, EvolutionEvent, EvolutionReport
from app.monitoring.engine import alerts_from_evolution, severity_allowed
from app.monitoring.models import AlertSeverity


def _report() -> EvolutionReport:
    return EvolutionReport(
        username="example",
        from_version=1,
        to_version=2,
        confidence=0.9,
        events=(
            EvolutionEvent(
                event_type="narrative_shift",
                category="narrative",
                title="Изменилось тематическое ядро",
                description="Новые устойчивые темы.",
                severity=ChangeSeverity.CRITICAL,
                confidence=0.94,
                old_value=["a"],
                new_value=["b"],
                evidence=(10, 11),
            ),
            EvolutionEvent(
                event_type="metric_shift",
                category="metrics",
                title="Активность выросла",
                description="Рост на 30%.",
                severity=ChangeSeverity.MEDIUM,
                confidence=0.8,
                old_value=10,
                new_value=13,
            ),
        ),
        executive_summary=("Изменилось тематическое ядро",),
    )


def test_sensitivity_thresholds() -> None:
    assert severity_allowed(AlertSeverity.CRITICAL, "critical")
    assert not severity_allowed(AlertSeverity.HIGH, "critical")
    assert severity_allowed(AlertSeverity.MEDIUM, "medium")
    assert not severity_allowed(AlertSeverity.LOW, "medium")


def test_alert_filtering_and_evidence() -> None:
    high = alerts_from_evolution(_report(), "high")
    assert len(high) == 1
    assert high[0].severity == AlertSeverity.CRITICAL
    assert high[0].evidence == (10, 11)
    all_alerts = alerts_from_evolution(_report(), "low")
    assert len(all_alerts) == 2


def test_alert_fingerprint_is_deterministic() -> None:
    first = alerts_from_evolution(_report(), "low")
    second = alerts_from_evolution(_report(), "low")
    assert [item.fingerprint for item in first] == [item.fingerprint for item in second]
    assert len(first[0].fingerprint) == 64
