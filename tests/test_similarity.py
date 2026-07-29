from datetime import UTC, datetime, timedelta

from app.domain.models import ChannelSnapshot, PostSnapshot
from app.profiling import build_content_dna
from app.similarity import compare_channels


def snapshot(name: str, shift: int = 0, emotional: bool = False) -> ChannelSnapshot:
    posts = []
    for index in range(1, 90):
        ending = "!!! 🔥" if emotional else "."
        text = f"Аналитика технологии рынок данные исследование номер {index % 7}{ending}"
        posts.append(PostSnapshot(index, datetime(2026, 1, 1, (index + shift) % 24, tzinfo=UTC) + timedelta(days=index // 24), text, 1000 + index, 10 + index % 5, 2, f"https://t.me/{name}/{index}"))
    return ChannelSnapshot(name, name, 1000, datetime.now(UTC), tuple(posts))


def test_identical_profiles_are_highly_similar():
    a = snapshot("alpha")
    b = snapshot("beta")
    result = compare_channels(a, build_content_dna(a), b, build_content_dna(b))
    assert result.overall_score > 0.95
    assert result.style_score > 0.95
    assert result.confidence > 0.5


def test_style_difference_reduces_style_score():
    a = snapshot("alpha")
    b = snapshot("beta", shift=8, emotional=True)
    result = compare_channels(a, build_content_dna(a), b, build_content_dna(b))
    assert result.style_score < 0.98
    assert result.temporal_score < 0.95
    assert "не доказывает" in result.explanation
