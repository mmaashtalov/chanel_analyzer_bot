from datetime import UTC, datetime, timedelta

from app.evidence.review import (
    ClaimReviewStatus,
    adjusted_scores,
    detect_evidence_gaps,
    recalculate_integrity,
    review_completeness,
)


def _bundle():
    now = datetime.now(UTC)
    return {
        "subject_type": "workspace_evolution_report",
        "subject_id": "w1:s1:s2",
        "claims": [
            {
                "claim_id": "c1",
                "category": "activity",
                "confidence": 0.8,
                "evidence_quality": 0.65,
                "evidence_ids": ["e1"],
                "review_status": "unreviewed",
                "review_version": 0,
            },
            {
                "claim_id": "c2",
                "category": "entities",
                "confidence": 0.7,
                "evidence_quality": 0.8,
                "evidence_ids": ["e2"],
                "review_status": "verified",
                "review_version": 1,
            },
        ],
        "evidence": [
            {"evidence_id": "e1", "kind": "computation", "content_hash": "a" * 64},
            {
                "evidence_id": "e2",
                "kind": "primary_document",
                "source_type": "telegram",
                "content_hash": "b" * 64,
                "published_at": (now - timedelta(days=1)).isoformat(),
            },
        ],
    }


def test_review_status_aliases():
    assert ClaimReviewStatus.parse("partial") is ClaimReviewStatus.PARTIALLY_VERIFIED
    assert ClaimReviewStatus.parse("needs_evidence") is ClaimReviewStatus.NEEDS_MORE_EVIDENCE


def test_adjusted_scores_are_bounded():
    assert adjusted_scores(0.98, 0.99, ClaimReviewStatus.VERIFIED) == (1.0, 1.0)
    assert adjusted_scores(0.8, 0.7, ClaimReviewStatus.REJECTED)[0] == 0.0


def test_review_completeness_counts_decisions():
    assert review_completeness(_bundle()["claims"]) == 0.5


def test_gap_detector_finds_missing_primary_and_source_diversity():
    gaps = detect_evidence_gaps(_bundle())
    codes_by_claim = {(gap.claim_id, gap.code) for gap in gaps}
    assert ("c1", "no_primary_document") in codes_by_claim
    assert ("c1", "low_evidence_quality") in codes_by_claim
    assert ("c2", "single_source_type") in codes_by_claim


def test_review_integrity_is_deterministic_and_status_sensitive():
    bundle = _bundle()
    first = recalculate_integrity(bundle)
    second = recalculate_integrity(bundle)
    assert first == second
    bundle["claims"][0]["review_status"] = "verified"
    bundle["claims"][0]["review_version"] = 1
    assert recalculate_integrity(bundle) != first
