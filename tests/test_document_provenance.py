from datetime import UTC, datetime, timedelta

from app.evidence.document_linker import SourceDocumentEvidence, rank_documents_for_claim
from app.evidence.engine import attach_document_evidence, build_workspace_evolution_provenance
from app.evidence.models import EvidenceKind
from app.workspace_evolution.engine import compare_workspace_snapshots


def _report():
    now = datetime.now(UTC)
    baseline = {
        "workspace_id": "w1", "generated_at": (now - timedelta(days=2)).isoformat(),
        "total_posts": 100, "coverage_ratio": 1.0, "weighted_confidence": 0.9,
        "mean_views": 1000, "mean_engagement_per_1000": 10, "mean_posts_per_day": 3,
        "top_entities": [], "top_domains": [], "top_keywords": [], "alert_counts": {},
    }
    current = {
        **baseline, "generated_at": now.isoformat(), "total_posts": 140,
        "top_entities": [("Ростех", 8)], "top_domains": [("example.org", 5)],
        "top_keywords": [("БПЛА", 7)], "alert_counts": {"high": 3},
    }
    return compare_workspace_snapshots(
        workspace_name="ОПК", baseline_snapshot_id="s1", current_snapshot_id="s2",
        baseline=baseline, current=current,
    )


def _documents(report):
    return (
        SourceDocumentEvidence(
            document_id="d1", source_id="source1", source_type="telegram",
            source_external_id="example_channel", title="Ростех представил БПЛА",
            body="Компания Ростех представила новую систему БПЛА. Подробности опубликованы на example.org.",
            author="Редакция", canonical_url="https://t.me/example_channel/10",
            published_at=report.current_generated_at - timedelta(hours=2),
            fingerprint="a" * 64, content_fingerprint="b" * 64,
        ),
        SourceDocumentEvidence(
            document_id="d2", source_id="source1", source_type="telegram",
            source_external_id="example_channel", title="Погода",
            body="Обычная публикация без связи с темой.", author=None,
            canonical_url="https://t.me/example_channel/11",
            published_at=report.current_generated_at - timedelta(hours=1),
            fingerprint="c" * 64, content_fingerprint="d" * 64,
        ),
    )


def test_document_ranking_prefers_matching_primary_material():
    report = _report()
    selected = rank_documents_for_claim(report, "entities", "Появились новые сущности", _documents(report))
    assert selected
    assert selected[0].document_id == "d1"


def test_document_evidence_is_attached_with_locator_excerpt_and_fingerprint():
    report = _report()
    base = build_workspace_evolution_provenance(report)
    enriched = attach_document_evidence(base, report, _documents(report))
    primary = [item for item in enriched.evidence if item.kind is EvidenceKind.PRIMARY_DOCUMENT]
    assert primary
    assert primary[0].canonical_url
    assert primary[0].excerpt
    assert primary[0].fingerprint == "a" * 64
    assert enriched.methodology_version == "document-provenance-v1"
    assert enriched.integrity_hash != base.integrity_hash


def test_document_linkage_is_deterministic():
    report = _report()
    base = build_workspace_evolution_provenance(report)
    first = attach_document_evidence(base, report, _documents(report))
    second = attach_document_evidence(base, report, _documents(report))
    assert first.bundle_id == second.bundle_id
    assert first.integrity_hash == second.integrity_hash


def test_serialized_primary_document_contains_audit_fields():
    report = _report()
    payload = attach_document_evidence(
        build_workspace_evolution_provenance(report), report, _documents(report)
    ).to_dict()
    primary = next(item for item in payload["evidence"] if item["kind"] == "primary_document")
    assert primary["document_id"] == "d1"
    assert primary["published_at"].endswith("+00:00")
    assert primary["content_hash"] == "b" * 64
