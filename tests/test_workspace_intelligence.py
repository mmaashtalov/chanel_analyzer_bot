from datetime import UTC, datetime

from app.workspace_intelligence.engine import build_workspace_intelligence
from app.workspace_intelligence.models import (
    ChannelIntelligence,
    CoverageStatus,
    WorkspaceAlertFact,
    WorkspaceIntelligenceInput,
)


def _channel(name: str, posts: int, confidence: float, views: float) -> ChannelIntelligence:
    return ChannelIntelligence(
        username=name,
        profile_version=2,
        posts_count=posts,
        confidence=confidence,
        mean_views=views,
        engagement_per_1000=12.0,
        posts_per_day=3.0,
    )


def test_complete_workspace_aggregation_is_weighted():
    report = build_workspace_intelligence(WorkspaceIntelligenceInput(
        workspace_id="w1",
        workspace_name="ОПК",
        requested_channels=("a", "b"),
        channels=(_channel("a", 100, 0.9, 1000), _channel("b", 20, 0.5, 5000)),
        generated_at=datetime(2026, 7, 28, tzinfo=UTC),
    ))
    assert report.coverage_status is CoverageStatus.COMPLETE
    assert report.total_posts == 120
    assert round(report.mean_views or 0, 2) == 1666.67
    assert round(report.weighted_confidence, 3) == 0.833


def test_partial_coverage_produces_explicit_finding():
    report = build_workspace_intelligence(WorkspaceIntelligenceInput(
        workspace_id="w1", workspace_name="ОПК",
        requested_channels=("a", "b"), channels=(_channel("a", 10, 0.8, 100),),
    ))
    assert report.coverage_status is CoverageStatus.PARTIAL
    assert report.coverage_ratio == 0.5
    assert any(item.category == "coverage" and "@b" in item.evidence for item in report.findings)


def test_empty_coverage_is_not_reported_as_zero_activity():
    report = build_workspace_intelligence(WorkspaceIntelligenceInput(
        workspace_id="w1", workspace_name="ОПК", requested_channels=("a",),
    ))
    assert report.coverage_status is CoverageStatus.EMPTY
    assert report.weighted_confidence == 0
    assert any("Нет аналитических профилей" == item.title for item in report.findings)


def test_alerts_and_ranked_objects_are_reflected():
    now = datetime.now(UTC)
    report = build_workspace_intelligence(WorkspaceIntelligenceInput(
        workspace_id="w1", workspace_name="ОПК", requested_channels=("a",),
        channels=(_channel("a", 10, 0.9, 100),),
        entity_mentions={"Ростех": 8, "ОАК": 3},
        domain_mentions={"example.ru": 4},
        keyword_mentions={"бпла": 2},
        alerts=(WorkspaceAlertFact("a", "high", "Новая тема", 0.92, now),),
    ))
    assert report.top_entities[0] == ("Ростех", 8)
    assert report.alert_counts["high"] == 1
    assert report.findings[0].severity == "high"


def test_serialization_contains_iso_datetimes():
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    report = build_workspace_intelligence(WorkspaceIntelligenceInput(
        workspace_id="w1", workspace_name="ОПК", requested_channels=("a",),
        channels=(ChannelIntelligence("a", 1, 1, 0.9, latest_collected_at=now),),
        generated_at=now,
    ))
    payload = report.to_dict()
    assert payload["generated_at"].endswith("+00:00")
    assert payload["channels"][0]["latest_collected_at"].endswith("+00:00")
