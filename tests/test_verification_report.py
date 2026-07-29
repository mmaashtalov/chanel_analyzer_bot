from pathlib import Path

from app.reports.verification_pdf import build_verification_exports


def test_verification_exports_are_created(tmp_path: Path):
    bundle = {
        "subject_type": "workspace_evolution_report",
        "subject_id": "w1:s1:s2",
        "methodology_version": "analyst-verification-v1",
        "completeness": 0.5,
        "review_completeness": 1.0,
        "integrity_hash": "a" * 64,
        "claims": [{
            "claim_id": "c1", "claim_index": 1, "category": "activity",
            "statement": "Рост активности", "confidence": 0.8,
            "evidence_quality": 0.9, "evidence_ids": ["e1"],
            "review_status": "verified", "review_comment": "Проверено",
            "review_version": 1,
        }],
        "evidence": [{
            "evidence_id": "e1", "kind": "primary_document",
            "source_type": "telegram", "content_hash": "b" * 64,
        }],
    }
    json_path, pdf_path = build_verification_exports(bundle, tmp_path)
    assert json_path.exists() and json_path.stat().st_size > 0
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
