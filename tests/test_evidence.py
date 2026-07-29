from datetime import UTC, datetime, timedelta

from app.evidence.engine import build_workspace_evolution_provenance
from app.evidence.models import EvidenceKind, EvidenceStrength
from app.workspace_evolution.engine import compare_workspace_snapshots


def _snapshot(when, posts, alerts=None):
    return {
        "workspace_id": "w1",
        "generated_at": when.isoformat(),
        "total_posts": posts,
        "coverage_ratio": 1.0,
        "weighted_confidence": 0.9,
        "mean_views": 1000,
        "mean_engagement_per_1000": 10,
        "mean_posts_per_day": 3,
        "top_entities": [],
        "top_domains": [],
        "top_keywords": [],
        "alert_counts": alerts or {},
    }


def _report():
    now = datetime.now(UTC)
    return compare_workspace_snapshots(
        workspace_name="ОПК",
        baseline_snapshot_id="s1",
        current_snapshot_id="s2",
        baseline=_snapshot(now - timedelta(days=1), 100, {"high": 1}),
        current=_snapshot(now, 160, {"high": 5}),
    )


def test_bundle_links_every_claim_to_snapshots_and_computations():
    bundle = build_workspace_evolution_provenance(_report())
    assert bundle.claims
    assert bundle.completeness == 1.0
    ids = {item.evidence_id for item in bundle.evidence}
    assert all(set(claim.evidence_ids) <= ids for claim in bundle.claims)
    assert any(item.kind is EvidenceKind.SNAPSHOT for item in bundle.evidence)
    assert any(item.kind is EvidenceKind.COMPUTATION for item in bundle.evidence)


def test_provenance_ids_and_integrity_are_deterministic_for_same_report():
    report = _report()
    first = build_workspace_evolution_provenance(report)
    second = build_workspace_evolution_provenance(report)
    assert first.bundle_id == second.bundle_id
    assert first.integrity_hash == second.integrity_hash
    assert [c.claim_id for c in first.claims] == [c.claim_id for c in second.claims]


def test_evidence_quality_is_bounded_and_has_caveats():
    bundle = build_workspace_evolution_provenance(_report())
    assert all(0 <= claim.evidence_quality <= 1 for claim in bundle.claims)
    assert all(claim.caveats for claim in bundle.claims)
    assert all(item.strength in EvidenceStrength for item in bundle.evidence)


def test_bundle_serialization_is_json_ready():
    payload = build_workspace_evolution_provenance(_report()).to_dict()
    assert payload["methodology_version"] == "evidence-provenance-v1"
    assert len(payload["integrity_hash"]) == 64
    assert payload["evidence"][0]["kind"] in {item.value for item in EvidenceKind}
