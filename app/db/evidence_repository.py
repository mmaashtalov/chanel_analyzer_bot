from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticClaimRecord,
    ClaimEvidenceLinkRecord,
    EvidenceReferenceRecord,
    ProvenanceBundleRecord,
    WorkspaceProvenanceLinkRecord,
)
from app.evidence.models import ProvenanceBundle


class EvidenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, bundle: ProvenanceBundle) -> str:
        async with self._session_factory() as session:
            existing = await session.get(ProvenanceBundleRecord, bundle.bundle_id)
            if existing is not None:
                existing.bundle_json = bundle.to_dict()
                existing.completeness = bundle.completeness
                await session.commit()
                return existing.id

            record = ProvenanceBundleRecord(
                id=bundle.bundle_id,
                subject_type=bundle.subject_type,
                subject_id=bundle.subject_id,
                methodology_version=bundle.methodology_version,
                completeness=bundle.completeness,
                review_completeness=0.0,
                integrity_hash=bundle.integrity_hash,
                bundle_json=bundle.to_dict(),
            )
            session.add(record)
            await session.flush()

            for evidence in bundle.evidence:
                session.add(EvidenceReferenceRecord(
                    id=evidence.evidence_id,
                    bundle_id=bundle.bundle_id,
                    kind=evidence.kind.value,
                    source_id=evidence.source_id,
                    locator=evidence.locator,
                    label=evidence.label,
                    strength=evidence.strength.value,
                    observed_at=evidence.observed_at,
                    value_json=evidence.value,
                    content_hash=evidence.content_hash,
                    document_id=evidence.document_id,
                    source_type=evidence.source_type,
                    canonical_url=evidence.canonical_url,
                    author=evidence.author,
                    excerpt=evidence.excerpt,
                    published_at=evidence.published_at,
                    fingerprint=evidence.fingerprint,
                ))
            for claim in bundle.claims:
                session.add(AnalyticClaimRecord(
                    id=claim.claim_id,
                    bundle_id=bundle.bundle_id,
                    claim_index=claim.claim_index,
                    category=claim.category,
                    statement=claim.statement,
                    assessment=claim.assessment,
                    severity=claim.severity,
                    confidence=claim.confidence,
                    evidence_quality=claim.evidence_quality,
                    caveats_json=list(claim.caveats),
                ))
                for evidence_id in claim.evidence_ids:
                    session.add(ClaimEvidenceLinkRecord(claim_id=claim.claim_id, evidence_id=evidence_id))
            await session.commit()
            return bundle.bundle_id

    async def get(self, bundle_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.get(ProvenanceBundleRecord, bundle_id)
            return None if row is None else row.bundle_json

    async def latest_for_subject(self, subject_type: str, subject_id: str) -> dict | None:
        query = (
            select(ProvenanceBundleRecord)
            .where(
                ProvenanceBundleRecord.subject_type == subject_type,
                ProvenanceBundleRecord.subject_id == subject_id,
            )
            .order_by(ProvenanceBundleRecord.created_at.desc())
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).scalar_one_or_none()
            return None if row is None else row.bundle_json

    async def link_to_workspace(
        self,
        bundle_id: str,
        workspace_id: str,
        source_item: str,
        link_type: str = "channel_analysis",
    ) -> bool:
        """Create a durable, idempotent association between a bundle and Workspace."""
        async with self._session_factory() as session:
            bundle = await session.get(ProvenanceBundleRecord, bundle_id)
            if bundle is None:
                raise LookupError("Provenance bundle не найден")
            existing = (await session.execute(
                select(WorkspaceProvenanceLinkRecord).where(
                    WorkspaceProvenanceLinkRecord.workspace_id == workspace_id,
                    WorkspaceProvenanceLinkRecord.bundle_id == bundle_id,
                )
            )).scalar_one_or_none()
            if existing is not None:
                return False
            session.add(WorkspaceProvenanceLinkRecord(
                workspace_id=workspace_id,
                bundle_id=bundle_id,
                link_type=link_type,
                source_item=source_item,
            ))
            await session.commit()
            return True
