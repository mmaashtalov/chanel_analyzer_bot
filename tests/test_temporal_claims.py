from app.evidence.temporal import (
    ClaimRelationType,
    ClaimSnapshot,
    classify_relation,
    stable_claim_identity,
    text_similarity,
    timeline_integrity,
)


def snapshot(claim_id: str, statement: str, assessment: str = "") -> ClaimSnapshot:
    return ClaimSnapshot(claim_id, "activity", statement, assessment, "2026-07-28T00:00:00+00:00", 0.8)


def test_identity_ignores_changed_numeric_value() -> None:
    assert stable_claim_identity("activity", "Объём публикаций вырос на 55%") == stable_claim_identity(
        "activity", "Объём публикаций вырос на 80%"
    )


def test_numeric_change_is_update() -> None:
    result = classify_relation(
        snapshot("a", "Объём публикаций вырос на 55%"),
        snapshot("b", "Объём публикаций вырос на 80%"),
    )
    assert result.relation_type is ClaimRelationType.UPDATES
    assert "numeric_value_changed" in result.rationale


def test_direction_change_is_contradiction() -> None:
    result = classify_relation(
        snapshot("a", "Наблюдается рост активности"),
        snapshot("b", "Наблюдается снижение активности"),
    )
    assert result.relation_type is ClaimRelationType.CONTRADICTS


def test_repeated_assertion_supports_previous() -> None:
    result = classify_relation(
        snapshot("a", "Количество критических сигналов увеличилось"),
        snapshot("b", "Количество критических сигналов увеличилось"),
    )
    assert result.relation_type is ClaimRelationType.SUPPORTS
    assert result.confidence > 0.9


def test_timeline_integrity_is_order_independent() -> None:
    first = timeline_integrity(["b", "a"], [("a", "b", "updates")])
    second = timeline_integrity(["a", "b"], [("a", "b", "updates")])
    assert first == second


def test_text_similarity_is_bounded() -> None:
    score = text_similarity("Новая тема испытаний", "Новая тема испытаний БПЛА")
    assert 0.0 <= score <= 1.0


def test_identity_survives_direction_flip() -> None:
    assert stable_claim_identity("activity", "Наблюдается рост активности") == stable_claim_identity(
        "activity", "Наблюдается снижение активности"
    )
