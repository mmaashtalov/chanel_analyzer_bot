from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.analytics.metrics import QuantitativeMetrics
from app.domain.models import ChannelSnapshot
from app.evidence.document_linker import (
    SourceDocumentEvidence,
    excerpt_for,
    rank_documents_for_claim,
)
from app.evidence.models import (
    AnalyticClaim,
    EvidenceKind,
    EvidenceReference,
    EvidenceStrength,
    ProvenanceBundle,
)
from app.profiling.models import ContentDNAProfile
from app.sources.models import UnifiedDocument
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


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def _document_excerpt(document: UnifiedDocument, max_chars: int = 420) -> str:
    text = " ".join(document.body.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def build_channel_analysis_provenance(
    snapshot: ChannelSnapshot,
    documents: tuple[UnifiedDocument, ...],
    metrics: QuantitativeMetrics,
    content_dna: ContentDNAProfile,
    *,
    job_id: str,
    document_record_ids: Mapping[str, str] | None = None,
    collection_stats: Mapping[str, Any] | None = None,
    workspace_ids: tuple[str, ...] = (),
    document_limit: int = 200,
) -> ProvenanceBundle:
    """Build a deterministic evidence package for one channel analysis.

    The analysis job is kept as operational metadata only.  Bundle and evidence
    identities are derived from the source content and calculations, so rerunning
    the same input does not create a second logical provenance package.
    """
    document_record_ids = document_record_ids or {}
    ordered_documents = tuple(sorted(documents, key=lambda item: (item.published_at, item.document_id)))
    limit = max(1, document_limit)
    selected_documents = ordered_documents[:limit]
    subject_id = f"telegram:{snapshot.username}"
    input_fingerprint = _hash_payload({
        "source_id": snapshot.username,
        "documents": [
            {
                "document_id": item.document_id,
                "fingerprint": item.fingerprint,
                "published_at": item.published_at.astimezone(UTC).isoformat(),
            }
            for item in ordered_documents
        ],
    })

    snapshot_evidence = EvidenceReference(
        evidence_id=_stable_id("evsnapshot", subject_id, input_fingerprint),
        kind=EvidenceKind.SNAPSHOT,
        source_id=snapshot.username,
        locator=f"telegram_snapshot:{snapshot.username}:{input_fingerprint[:16]}",
        label=f"Снимок публикаций @{snapshot.username}",
        strength=EvidenceStrength.DIRECT,
        observed_at=snapshot.collected_at,
        value={
            "channel": snapshot.username,
            "title": snapshot.title,
            "subscribers": snapshot.subscribers,
            "input_document_count": len(ordered_documents),
            "document_ids": [item.document_id for item in ordered_documents],
            "document_fingerprints": [item.fingerprint for item in ordered_documents],
        },
        content_hash=input_fingerprint,
        source_type="telegram",
    )
    evidence_by_id: dict[str, EvidenceReference] = {snapshot_evidence.evidence_id: snapshot_evidence}

    def add_computation(key: str, value: Any, label: str) -> EvidenceReference:
        content_hash = _hash_payload({"key": key, "value": value})
        reference = EvidenceReference(
            evidence_id=_stable_id("evcalc", subject_id, key, content_hash),
            kind=EvidenceKind.COMPUTATION,
            source_id=f"analysis:{snapshot.username}",
            locator=f"channel_analysis.{key}",
            label=label,
            strength=EvidenceStrength.DIRECT,
            observed_at=snapshot.collected_at,
            value=value,
            content_hash=content_hash,
            source_type="telegram",
        )
        evidence_by_id[reference.evidence_id] = reference
        return reference

    input_count = add_computation(
        "input.posts_count",
        len(ordered_documents),
        "Количество сохранённых текстовых публикаций",
    )
    metric_payload = metrics.to_dict()
    metric_references: dict[str, EvidenceReference] = {}
    for key, label in (
        ("mean_views", "Средний охват публикации"),
        ("engagement_per_1000_views", "ER на 1 000 просмотров"),
        ("mean_post_length", "Средняя длина публикации"),
        ("posts_per_day", "Публикаций в день"),
    ):
        value = metric_payload.get(key)
        if value is not None:
            metric_references[key] = add_computation(f"metrics.{key}", value, label)

    trait = max(content_dna.traits, key=lambda item: (item.score, item.name), default=None)
    trait_reference = None
    if trait is not None:
        trait_reference = add_computation(
            f"content_dna.traits.{trait.name}",
            {"score": trait.score, "confidence": trait.confidence},
            f"Content DNA: {trait.name}",
        )

    primary_ids: list[str] = []
    for document in selected_documents:
        evidence_id = _stable_id("evdoc", subject_id, document.document_id, document.fingerprint)
        reference = EvidenceReference(
            evidence_id=evidence_id,
            kind=EvidenceKind.PRIMARY_DOCUMENT,
            source_id=document.source_id,
            locator=document.canonical_url or f"telegram:{document.source_id}/{document.document_id}",
            label=document.title or f"Публикация @{document.source_id} #{document.document_id}",
            strength=EvidenceStrength.DIRECT,
            observed_at=document.published_at,
            value={
                "external_document_id": document.document_id,
                "metadata": document.metadata,
            },
            content_hash=document.content_fingerprint,
            document_id=document_record_ids.get(document.document_id)
            or document_record_ids.get(document.fingerprint),
            source_type=document.source_type.value,
            canonical_url=document.canonical_url,
            author=document.author,
            excerpt=_document_excerpt(document),
            published_at=document.published_at,
            fingerprint=document.fingerprint,
        )
        evidence_by_id[evidence_id] = reference
        primary_ids.append(evidence_id)

    shared_evidence = [snapshot_evidence.evidence_id, input_count.evidence_id, *primary_ids]
    claims: list[AnalyticClaim] = []

    def add_claim(
        index: int,
        category: str,
        statement: str,
        assessment: str,
        confidence: float,
        evidence_ids: list[str],
        caveats: tuple[str, ...],
    ) -> None:
        claims.append(AnalyticClaim(
            claim_id=_stable_id("claim", subject_id, category, statement),
            claim_index=index,
            category=category,
            statement=statement,
            assessment=assessment,
            severity="low",
            confidence=_bounded(confidence),
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            evidence_quality=_bounded(0.42 + 0.11 * min(len(selected_documents), 5)),
            caveats=caveats,
        ))

    sample_confidence = min(1.0, len(ordered_documents) / 120)
    add_claim(
        1,
        "activity",
        f"В выбранном периоде зафиксировано {len(ordered_documents)} текстовых публикаций.",
        "Это наблюдение по сохранённому снимку Telegram, а не объяснение причин публикационной активности.",
        sample_confidence,
        shared_evidence,
        (
            "Полнота вывода зависит от доступности канала и заданного периода сбора.",
        ),
    )

    next_index = 2
    for key, label, formatter in (
        ("mean_views", "Средний охват", lambda value: f"{float(value):.2f}"),
        ("engagement_per_1000_views", "ER на 1 000 просмотров", lambda value: f"{float(value):.2f}"),
    ):
        value = metric_payload.get(key)
        reference = metric_references.get(key)
        if value is None or reference is None:
            continue
        add_claim(
            next_index,
            "metrics",
            f"{label} составил {formatter(value)}.",
            "Показатель рассчитан детерминированно по сохранённым публикациям и доступным Telegram-метрикам.",
            min(1.0, 0.55 + sample_confidence * 0.4),
            [snapshot_evidence.evidence_id, reference.evidence_id, *primary_ids],
            (
                "Расчёт не устанавливает причин изменения охвата или вовлечённости.",
                "Показатели Telegram могут быть недоступны для части публикаций.",
            ),
        )
        next_index += 1

    if trait is not None and trait_reference is not None:
        add_claim(
            next_index,
            "content_dna",
            f"Наиболее выраженный измеримый признак Content DNA — «{trait.name}» ({trait.score:.0%}).",
            trait.explanation,
            min(content_dna.confidence, trait.confidence),
            [snapshot_evidence.evidence_id, trait_reference.evidence_id, *primary_ids],
            tuple(content_dna.limitations[:2]) or (
                "Профиль описывает публикационный стиль, а не личность автора.",
            ),
        )

    canonical = {
        "subject_type": "channel_analysis",
        "subject_id": subject_id,
        "methodology_version": "channel-evidence-first-v1",
        "claims": [
            {
                "claim_id": claim.claim_id,
                "statement": claim.statement,
                "evidence_ids": list(claim.evidence_ids),
                "confidence": claim.confidence,
                "evidence_quality": claim.evidence_quality,
            }
            for claim in claims
        ],
        "evidence": sorted(
            (item.evidence_id, item.content_hash, item.document_id, item.source_id)
            for item in evidence_by_id.values()
        ),
    }
    integrity_hash = _hash_payload(canonical)
    limitations = [
        "Пакет фиксирует наблюдаемые публикации и расчёты; наличие материала не доказывает авторство, координацию или намерение.",
        "Telegram-снимок зависит от доступности канала, прав чтения и заданного периода.",
    ]
    if len(selected_documents) < len(ordered_documents):
        limitations.append(
            f"В provenance включены первые {len(selected_documents)} документов из {len(ordered_documents)}; полный набор сохранён в Source Registry."
        )
    if not selected_documents:
        limitations.append("Первичные документы отсутствуют; claims опираются только на snapshot и вычисления.")

    safe_collection_stats = dict(collection_stats or {})
    safe_collection_stats.pop("document_ids", None)
    metadata = {
        "analysis_job_id": job_id,
        "source_type": "telegram",
        "source_id": snapshot.username,
        "input_document_count": len(ordered_documents),
        "linked_document_count": len(selected_documents),
        "omitted_document_count": max(0, len(ordered_documents) - len(selected_documents)),
        "primary_document_coverage": _bounded(
            len(selected_documents) / len(ordered_documents) if ordered_documents else 0.0
        ),
        "collection": safe_collection_stats,
        "workspace_ids": list(workspace_ids),
    }
    return ProvenanceBundle(
        bundle_id=_stable_id("bundle", subject_id, integrity_hash),
        subject_type="channel_analysis",
        subject_id=subject_id,
        methodology_version="channel-evidence-first-v1",
        generated_at=snapshot.collected_at,
        claims=tuple(claims),
        evidence=tuple(sorted(evidence_by_id.values(), key=lambda item: item.evidence_id)),
        completeness=1.0 if claims and all(claim.evidence_ids for claim in claims) else 0.0,
        integrity_hash=integrity_hash,
        limitations=tuple(limitations),
        metadata=metadata,
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
    documents: tuple[SourceDocumentEvidence, ...],
    per_claim_limit: int = 3,
) -> ProvenanceBundle:
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
