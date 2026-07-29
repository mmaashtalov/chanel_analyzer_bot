from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.evidence.models import (
    AnalyticClaim,
    EvidenceKind,
    EvidenceReference,
    EvidenceStrength,
    ProvenanceBundle,
)
from app.workspace_evolution.models import WorkspaceEvolutionReport

_NAMESPACE = uuid.UUID("9e8d78c2-3e47-46a0-932f-3948d9ef4468")


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{uuid.uuid5(_NAMESPACE, raw).hex}"


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _metric_evidence(report: WorkspaceEvolutionReport, category: str, evidence_text: str, index: int) -> EvidenceReference:
    locator = f"observations[{index}].evidence"
    value = evidence_text
    return EvidenceReference(
        evidence_id=_stable_id("ev", report.workspace_id, report.baseline_snapshot_id, report.current_snapshot_id, index, evidence_text),
        kind=EvidenceKind.COMPUTATION,
        source_id=f"{report.baseline_snapshot_id}:{report.current_snapshot_id}",
        locator=locator,
        label=f"Расчёт Workspace Evolution / {category}",
        strength=EvidenceStrength.DIRECT,
        observed_at=report.current_generated_at,
        value=value,
        content_hash=_hash_payload(value),
    )


def build_workspace_evolution_provenance(report: WorkspaceEvolutionReport) -> ProvenanceBundle:
    evidence_by_id: dict[str, EvidenceReference] = {}
    claims: list[AnalyticClaim] = []

    baseline_ref = EvidenceReference(
        evidence_id=_stable_id("ev", report.workspace_id, report.baseline_snapshot_id),
        kind=EvidenceKind.SNAPSHOT,
        source_id=report.baseline_snapshot_id,
        locator="workspace_intelligence_snapshot",
        label="Baseline Workspace Intelligence Snapshot",
        strength=EvidenceStrength.CONTEXTUAL,
        observed_at=report.baseline_generated_at,
        content_hash=_hash_payload({"id": report.baseline_snapshot_id, "at": report.baseline_generated_at.isoformat()}),
    )
    current_ref = EvidenceReference(
        evidence_id=_stable_id("ev", report.workspace_id, report.current_snapshot_id),
        kind=EvidenceKind.SNAPSHOT,
        source_id=report.current_snapshot_id,
        locator="workspace_intelligence_snapshot",
        label="Current Workspace Intelligence Snapshot",
        strength=EvidenceStrength.CONTEXTUAL,
        observed_at=report.current_generated_at,
        content_hash=_hash_payload({"id": report.current_snapshot_id, "at": report.current_generated_at.isoformat()}),
    )
    evidence_by_id[baseline_ref.evidence_id] = baseline_ref
    evidence_by_id[current_ref.evidence_id] = current_ref

    for index, observation in enumerate(report.observations, 1):
        evidence_ids = [baseline_ref.evidence_id, current_ref.evidence_id]
        for text in observation.evidence:
            ref = _metric_evidence(report, observation.category, text, index)
            evidence_by_id[ref.evidence_id] = ref
            evidence_ids.append(ref.evidence_id)

        direct_count = max(0, len(evidence_ids) - 2)
        quality = min(1.0, 0.45 + 0.14 * direct_count + 0.18 * min(report.confidence, observation.confidence))
        caveats = tuple(report.limitations[:2]) if quality < 0.8 else tuple(report.limitations[:1])
        claims.append(AnalyticClaim(
            claim_id=_stable_id("claim", report.workspace_id, report.baseline_snapshot_id, report.current_snapshot_id, index, observation.observation),
            claim_index=index,
            category=observation.category,
            statement=observation.observation,
            assessment=observation.assessment,
            severity=observation.severity,
            confidence=observation.confidence,
            evidence_ids=tuple(evidence_ids),
            evidence_quality=quality,
            caveats=caveats,
        ))

    evidenced = sum(1 for claim in claims if claim.evidence_ids)
    completeness = 1.0 if not claims else evidenced / len(claims)
    canonical = {
        "subject": report.workspace_id,
        "pair": [report.baseline_snapshot_id, report.current_snapshot_id],
        "claims": [claim.claim_id for claim in claims],
        "evidence": sorted(evidence_by_id),
    }
    integrity_hash = _hash_payload(canonical)
    bundle_id = _stable_id("bundle", report.workspace_id, report.baseline_snapshot_id, report.current_snapshot_id, integrity_hash)
    return ProvenanceBundle(
        bundle_id=bundle_id,
        subject_type="workspace_evolution_report",
        subject_id=f"{report.workspace_id}:{report.baseline_snapshot_id}:{report.current_snapshot_id}",
        methodology_version="evidence-provenance-v1",
        generated_at=datetime.now(UTC),
        claims=tuple(claims),
        evidence=tuple(sorted(evidence_by_id.values(), key=lambda item: item.evidence_id)),
        completeness=completeness,
        integrity_hash=integrity_hash,
        limitations=(
            "Snapshot и вычисление подтверждают зафиксированное изменение, но не устанавливают его внешнюю причину.",
            "До внедрения document-level linkage первичные публикации не входят в этот provenance bundle.",
        ),
    )


def attach_document_evidence(
    bundle: ProvenanceBundle,
    report: WorkspaceEvolutionReport,
    documents: tuple["SourceDocumentEvidence", ...],
    per_claim_limit: int = 3,
) -> ProvenanceBundle:
    from app.evidence.document_linker import excerpt_for, rank_documents_for_claim

    evidence_by_id = {item.evidence_id: item for item in bundle.evidence}
    claims: list[AnalyticClaim] = []
    linked_document_ids: set[str] = set()
    for claim in bundle.claims:
        selected = rank_documents_for_claim(report, claim.category, claim.statement, documents, per_claim_limit)
        evidence_ids = list(claim.evidence_ids)
        terms = set()
        for name, _ in (
            report.added_entities + report.removed_entities + report.added_domains + report.removed_domains
            + report.added_keywords + report.removed_keywords
        ):
            terms.add(name.casefold())
        for document in selected:
            evidence_id = _stable_id("evdoc", document.document_id, document.fingerprint)
            ref = EvidenceReference(
                evidence_id=evidence_id,
                kind=EvidenceKind.PRIMARY_DOCUMENT,
                source_id=document.source_id,
                locator=document.canonical_url or f"source_document:{document.document_id}",
                label=document.title or f"Документ {document.source_external_id}",
                strength=EvidenceStrength.CORROBORATING,
                observed_at=document.published_at,
                value={"source_external_id": document.source_external_id},
                content_hash=document.content_fingerprint,
                document_id=document.document_id,
                source_type=document.source_type,
                canonical_url=document.canonical_url,
                author=document.author,
                excerpt=excerpt_for(document, terms),
                published_at=document.published_at,
                fingerprint=document.fingerprint,
            )
            evidence_by_id[evidence_id] = ref
            evidence_ids.append(evidence_id)
            linked_document_ids.add(document.document_id)
        doc_count = len(selected)
        quality = min(1.0, claim.evidence_quality + min(0.24, 0.08 * doc_count))
        caveats = tuple(c for c in claim.caveats if "document-level" not in c.casefold())
        if not selected:
            caveats += ("Подходящие первичные документы в хранилище Workspace не найдены.",)
        claims.append(AnalyticClaim(
            claim_id=claim.claim_id,
            claim_index=claim.claim_index,
            category=claim.category,
            statement=claim.statement,
            assessment=claim.assessment,
            severity=claim.severity,
            confidence=claim.confidence,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            evidence_quality=quality,
            caveats=caveats,
        ))

    document_claims = sum(
        1 for claim in claims
        if any(evidence_by_id[eid].kind == EvidenceKind.PRIMARY_DOCUMENT for eid in claim.evidence_ids)
    )
    completeness = 1.0 if not claims else document_claims / len(claims)
    canonical = {
        "subject": bundle.subject_id,
        "claims": [claim.claim_id for claim in claims],
        "evidence": sorted((eid, evidence_by_id[eid].content_hash) for eid in evidence_by_id),
    }
    integrity_hash = _hash_payload(canonical)
    bundle_id = _stable_id("bundle", bundle.subject_id, integrity_hash)
    limitations = (
        "Первичные документы подтверждают наличие наблюдаемого материала, но сами по себе не доказывают внешнюю причину изменения.",
        "Document-level linkage зависит от полноты локального хранилища источников и правил сопоставления Workspace.",
    )
    return ProvenanceBundle(
        bundle_id=bundle_id,
        subject_type=bundle.subject_type,
        subject_id=bundle.subject_id,
        methodology_version="document-provenance-v1",
        generated_at=bundle.generated_at,
        claims=tuple(claims),
        evidence=tuple(sorted(evidence_by_id.values(), key=lambda item: item.evidence_id)),
        completeness=completeness,
        integrity_hash=integrity_hash,
        limitations=limitations,
    )
