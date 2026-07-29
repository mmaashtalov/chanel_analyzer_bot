from datetime import UTC, datetime, timedelta

from app.workspace_evolution.engine import compare_workspace_snapshots
from app.workspace_evolution.models import WorkspaceTrend


def snapshot(*, posts=100, coverage=1.0, entities=(), domains=(), keywords=(), alerts=None, when=None):
    return {
        "workspace_id": "w1",
        "generated_at": (when or datetime.now(UTC)).isoformat(),
        "total_posts": posts,
        "coverage_ratio": coverage,
        "weighted_confidence": 0.9,
        "mean_views": 1000.0,
        "mean_engagement_per_1000": 10.0,
        "mean_posts_per_day": 3.0,
        "top_entities": list(entities),
        "top_domains": list(domains),
        "top_keywords": list(keywords),
        "alert_counts": alerts or {},
    }


def compare(old, new):
    return compare_workspace_snapshots(
        workspace_name="ОПК", baseline_snapshot_id="s1", current_snapshot_id="s2",
        baseline=old, current=new,
    )


def test_stable_when_changes_are_small():
    now = datetime.now(UTC)
    report = compare(snapshot(posts=100, when=now-timedelta(days=1)), snapshot(posts=105, when=now))
    assert report.trend is WorkspaceTrend.STABLE
    assert report.confidence > 0.7


def test_escalating_requires_activity_and_important_alerts():
    now = datetime.now(UTC)
    report = compare(
        snapshot(posts=100, alerts={"high": 1}, when=now-timedelta(days=1)),
        snapshot(posts=150, alerts={"high": 5}, when=now),
    )
    assert report.trend is WorkspaceTrend.ESCALATING
    assert any(item.category == "alerts" for item in report.observations)


def test_new_objects_and_topics_are_reported():
    now = datetime.now(UTC)
    report = compare(
        snapshot(entities=(("A", 2),), domains=(("a.ru", 2),), when=now-timedelta(days=1)),
        snapshot(entities=(("A", 2), ("B", 5)), domains=(("a.ru", 2), ("b.ru", 3)), keywords=(("x",1),("y",1),("z",1)), when=now),
    )
    assert report.added_entities == (("B", 5),)
    assert report.added_domains == (("b.ru", 3),)
    assert report.trend is WorkspaceTrend.EMERGING_NARRATIVE


def test_coverage_drop_marks_insufficient_data():
    now = datetime.now(UTC)
    report = compare(snapshot(coverage=1.0, when=now-timedelta(days=1)), snapshot(coverage=0.5, when=now))
    assert report.trend is WorkspaceTrend.INSUFFICIENT_DATA
    assert any(item.category == "coverage" for item in report.observations)


def test_report_serialization_is_json_ready():
    now = datetime.now(UTC)
    payload = compare(snapshot(when=now-timedelta(days=1)), snapshot(when=now)).to_dict()
    assert payload["trend"] == "stable"
    assert payload["current_generated_at"].endswith("+00:00")
