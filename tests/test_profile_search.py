from datetime import UTC, datetime

from app.profiles.models import IntelligenceProfile
from app.similarity.search import classify_similarity, score_profiles


def unit(size: int, index: int = 0) -> tuple[float, ...]:
    values = [0.0] * size
    values[index] = 1.0
    return tuple(values)


def profile(
    username: str,
    style: tuple[float, ...],
    narrative: tuple[float, ...],
    temporal: tuple[float, ...],
    structural: tuple[float, ...],
) -> IntelligenceProfile:
    combined = style + temporal + structural + narrative
    return IntelligenceProfile(
        username=username,
        title=username,
        subscribers=1000,
        collected_at=datetime.now(UTC),
        source_post_count=120,
        methodology_version="test",
        style_vector=style,
        temporal_vector=temporal,
        structural_vector=structural,
        narrative_vector=narrative,
        combined_vector=combined,
        metrics={},
        content_dna={},
        confidence=0.9,
    )


def test_identical_profiles_score_high() -> None:
    source = profile("a", unit(16), unit(64), unit(168), unit(8))
    candidate = profile("b", unit(16), unit(64), unit(168), unit(8))
    result = score_profiles(source, candidate, 2)
    assert result.overall_score == 1.0
    assert result.classification == "Практически идентичные профили"
    assert result.confidence >= 0.9


def test_narrative_only_cannot_create_high_match() -> None:
    source = profile("a", unit(16, 0), unit(64, 0), unit(168, 0), unit(8, 0))
    candidate = profile("b", unit(16, 1), unit(64, 0), unit(168, 1), unit(8, 1))
    result = score_profiles(source, candidate, 1)
    assert result.narrative_score == 1.0
    assert result.style_score == 0.0
    assert result.overall_score <= 0.49


def test_similarity_classification_boundaries() -> None:
    assert classify_similarity(0.95).startswith("Практически")
    assert classify_similarity(0.85).startswith("Очень")
    assert classify_similarity(0.70).startswith("Похожий")
    assert classify_similarity(0.50).startswith("Частичные")
    assert classify_similarity(0.49).startswith("Значимых")
