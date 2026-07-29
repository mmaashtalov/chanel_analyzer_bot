from datetime import UTC, datetime

from app.analytics.metrics import calculate_metrics
from app.domain.models import ChannelSnapshot, PostSnapshot


def test_calculate_metrics() -> None:
    snapshot = ChannelSnapshot(
        username="demo",
        title="Demo",
        subscribers=1000,
        collected_at=datetime.now(UTC),
        posts=(
            PostSnapshot(1, datetime(2026, 1, 1, tzinfo=UTC), "abc", views=100, reactions=10),
            PostSnapshot(2, datetime(2026, 1, 2, tzinfo=UTC), "abcdef", views=300, reactions=30),
        ),
    )
    metrics = calculate_metrics(snapshot)
    assert metrics.posts_count == 2
    assert metrics.mean_views == 200
    assert metrics.median_views == 200
    assert metrics.max_views == 300
    assert metrics.mean_reactions == 20
    assert metrics.mean_post_length == 4.5
    assert metrics.engagement_per_1000_views == 100
    assert metrics.median_interval_hours == 24
