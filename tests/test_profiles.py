from datetime import UTC, datetime, timedelta

from app.analytics.metrics import calculate_metrics
from app.domain.models import ChannelSnapshot, PostSnapshot
from app.profiling import build_content_dna
from app.profiles import VECTOR_DIM, build_intelligence_profile


def build_snapshot(count: int) -> ChannelSnapshot:
    posts = tuple(
        PostSnapshot(
            message_id=index,
            published_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index * 7),
            text=("Аналитический обзор технологии и рынка. " * (index % 12 + 1)).strip(),
            views=1000 + index * 17,
            reactions=5 + index % 20,
            forwards=index % 8,
            url=f"https://t.me/demo/{index}",
        )
        for index in range(1, count + 1)
    )
    return ChannelSnapshot("demo", "Demo", 12000, datetime.now(UTC), posts)


def test_intelligence_profile_has_stable_dimension() -> None:
    snapshot = build_snapshot(140)
    dna = build_content_dna(snapshot)
    profile = build_intelligence_profile(snapshot, dna, calculate_metrics(snapshot).to_dict())
    assert len(profile.combined_vector) == VECTOR_DIM == 256
    assert len(profile.style_vector) == 16
    assert len(profile.temporal_vector) == 168
    assert len(profile.structural_vector) == 8
    assert len(profile.narrative_vector) == 64
    assert 0 <= profile.confidence <= 1


def test_profile_vector_is_deterministic() -> None:
    snapshot = build_snapshot(80)
    dna = build_content_dna(snapshot)
    first = build_intelligence_profile(snapshot, dna, {})
    second = build_intelligence_profile(snapshot, dna, {})
    assert first.combined_vector == second.combined_vector
