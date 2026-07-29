from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticClaimRecord,
    ClaimEvidenceLinkRecord,
    EvidenceReferenceRecord,
    ProvenanceBundleRecord,
)
from app.evidence.corroboration import DocumentSignal, assess_claim_corroboration
from app.evidence.review import recalculate_integrity


class CorroborationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def assess_bundle(self, bundle_id: str) -> dict:
        async with self._session_factory() as session:
            bundle = await session.get(ProvenanceBundleRecord, bundle_id)
            if bundle is None:
                raise LookupError("Provenance bundle не найден")

            claims = list((await session.execute(
                select(AnalyticClaimRecord)
                .where(AnalyticClaimRecord.bundle_id == bundle_id)
                .order_by(AnalyticClaimRecord.claim_index)
            )).scalars().all())

            payload = dict(bundle.bundle_json)
            payload_claims = {str(item["claim_id"]): item for item in payload.get("claims", [])}
            assessments: list[dict] = []

            for claim in claims:
                rows = (await session.execute(
                    select(EvidenceReferenceRecord)
                    .join(ClaimEvidenceLinkRecord, ClaimEvidenceLinkRecord.evidence_id == EvidenceReferenceRecord.id)
                    .where(
                        ClaimEvidenceLinkRecord.claim_id == claim.id,
                        EvidenceReferenceRecord.kind == "primary_document",
                    )
                )).scalars().all()
                result = assess_claim_corroboration(
                    claim.id,
                    tuple(DocumentSignal(
                        evidence_id=row.id,
                        source_id=row.source_id,
                        source_type=row.source_type,
                        canonical_url=row.canonical_url,
                        content_hash=row.content_hash,
                        fingerprint=row.fingerprint,
                        excerpt=row.excerpt,
                    ) for row in rows),
                )
                claim.independence_score = result.independence_score
                claim.corroboration_score = result.corroboration_score
                claim.corroboration_json = {
                    "document_count": result.document_count,
                    "independent_cluster_count": result.independent_cluster_count,
                    "clusters": [
                        {
                            "cluster_id": cluster.cluster_id,
                            "evidence_ids": list(cluster.evidence_ids),
                            "source_ids": list(cluster.source_ids),
                            "source_types": list(cluster.source_types),
                            "upstream_domains": list(cluster.upstream_domains),
                            "reason": cluster.reason,
                        }
                        for cluster in result.clusters
                    ],
                    "caveats": list(result.caveats),
                }
                claim_payload = payload_claims.get(claim.id)
                if claim_payload is not None:
                    claim_payload["independence_score"] = result.independence_score
                    claim_payload["corroboration_score"] = result.corroboration_score
                    claim_payload["corroboration"] = claim.corroboration_json
                    if result.independent_cluster_count < 2 and claim_payload.get("review_status") == "verified":
                        claim_payload["review_status"] = "partially_verified"
                        claim.review_status = "partially_verified"
                assessments.append({
                    "claim_id": claim.id,
                    "statement": claim.statement,
                    "independence_score": result.independence_score,
                    "corroboration_score": result.corroboration_score,
                    **claim.corroboration_json,
                })

            payload["claims"] = list(payload_claims.values())
            payload["methodology_version"] = "source-independence-v1"
            payload["integrity_hash"] = recalculate_integrity(payload)
            bundle.methodology_version = "source-independence-v1"
            bundle.integrity_hash = payload["integrity_hash"]
            bundle.bundle_json = payload
            await session.commit()
            return {
                "bundle_id": bundle_id,
                "subject_id": bundle.subject_id,
                "methodology_version": bundle.methodology_version,
                "integrity_hash": bundle.integrity_hash,
                "claims": assessments,
            }
