from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticClaimRecord,
    ClaimIdentityRecord,
    ClaimTimelineLinkRecord,
    ProvenanceBundleRecord,
)
from app.evidence.review import recalculate_integrity
from app.evidence.temporal import (
    ClaimRelationType,
    ClaimSnapshot,
    TemporalClaimStatus,
    classify_relation,
    stable_claim_identity,
    timeline_integrity,
)


class TemporalClaimRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def build_workspace_timeline(self, workspace_id: str) -> dict:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(AnalyticClaimRecord, ProvenanceBundleRecord)
                .join(ProvenanceBundleRecord, ProvenanceBundleRecord.id == AnalyticClaimRecord.bundle_id)
                .where(ProvenanceBundleRecord.subject_id.like(f"{workspace_id}:%"))
                .order_by(ProvenanceBundleRecord.created_at, AnalyticClaimRecord.claim_index)
            )).all()
            if not rows:
                raise LookupError("Для Workspace ещё нет claims")

            grouped: dict[str, list[tuple[AnalyticClaimRecord, ProvenanceBundleRecord]]] = {}
            for claim, bundle in rows:
                identity_id = stable_claim_identity(claim.category, claim.statement)
                grouped.setdefault(identity_id, []).append((claim, bundle))

            await session.execute(delete(ClaimTimelineLinkRecord).where(
                ClaimTimelineLinkRecord.workspace_id == workspace_id
            ))
            report_identities: list[dict] = []
            relation_tuples: list[tuple[str, str, str]] = []

            for identity_id, items in grouped.items():
                identity = await session.get(ClaimIdentityRecord, identity_id)
                if identity is None:
                    first_claim = items[0][0]
                    identity = ClaimIdentityRecord(
                        id=identity_id,
                        workspace_id=workspace_id,
                        category=first_claim.category,
                        canonical_statement=first_claim.statement,
                        methodology_version="temporal-claims-v1",
                    )
                    session.add(identity)
                identity.updated_at = datetime.now(UTC)

                timeline: list[dict] = []
                previous_pair: tuple[AnalyticClaimRecord, ProvenanceBundleRecord] | None = None
                for claim, bundle in items:
                    claim.claim_identity_id = identity_id
                    claim.temporal_status = TemporalClaimStatus.CURRENT.value
                    relation_payload = None
                    if previous_pair is not None:
                        previous, previous_bundle = previous_pair
                        relation = classify_relation(
                            ClaimSnapshot(previous.id, previous.category, previous.statement, previous.assessment,
                                          previous_bundle.created_at.isoformat(), previous.confidence),
                            ClaimSnapshot(claim.id, claim.category, claim.statement, claim.assessment,
                                          bundle.created_at.isoformat(), claim.confidence),
                        )
                        link_id = str(uuid.uuid4())
                        event_hash = hashlib.sha256(
                            f"{previous.id}|{claim.id}|{relation.relation_type.value}|{relation.confidence:.6f}".encode("utf-8")
                        ).hexdigest()
                        session.add(ClaimTimelineLinkRecord(
                            id=link_id,
                            workspace_id=workspace_id,
                            claim_identity_id=identity_id,
                            source_claim_id=previous.id,
                            target_claim_id=claim.id,
                            relation_type=relation.relation_type.value,
                            confidence=relation.confidence,
                            rationale_json=list(relation.rationale),
                            event_hash=event_hash,
                        ))
                        relation_tuples.append((previous.id, claim.id, relation.relation_type.value))
                        if relation.relation_type is ClaimRelationType.CONTRADICTS:
                            previous.temporal_status = TemporalClaimStatus.CONTRADICTED.value
                            claim.temporal_status = TemporalClaimStatus.CONTRADICTED.value
                        else:
                            previous.temporal_status = TemporalClaimStatus.SUPERSEDED.value
                        relation_payload = {
                            "from_claim_id": previous.id,
                            "type": relation.relation_type.value,
                            "confidence": relation.confidence,
                            "rationale": list(relation.rationale),
                        }
                    timeline.append({
                        "claim_id": claim.id,
                        "bundle_id": bundle.id,
                        "generated_at": bundle.created_at.isoformat(),
                        "statement": claim.statement,
                        "assessment": claim.assessment,
                        "confidence": claim.confidence,
                        "review_status": claim.review_status,
                        "temporal_status": claim.temporal_status,
                        "relation_from_previous": relation_payload,
                    })
                    previous_pair = (claim, bundle)

                report_identities.append({
                    "claim_identity_id": identity_id,
                    "category": identity.category,
                    "canonical_statement": identity.canonical_statement,
                    "timeline": timeline,
                })

            # Embed temporal metadata in every affected provenance bundle.
            bundle_map: dict[str, ProvenanceBundleRecord] = {bundle.id: bundle for _, bundle in rows}
            claim_map = {claim.id: claim for claim, _ in rows}
            for bundle in bundle_map.values():
                payload = dict(bundle.bundle_json)
                for claim_payload in payload.get("claims", []):
                    record = claim_map.get(str(claim_payload.get("claim_id")))
                    if record is not None:
                        claim_payload["claim_identity_id"] = record.claim_identity_id
                        claim_payload["temporal_status"] = record.temporal_status
                payload["methodology_version"] = "temporal-claims-v1"
                payload["integrity_hash"] = recalculate_integrity(payload)
                bundle.bundle_json = payload
                bundle.methodology_version = "temporal-claims-v1"
                bundle.integrity_hash = payload["integrity_hash"]

            integrity = timeline_integrity(
                (claim.id for claim, _ in rows),
                relation_tuples,
            )
            await session.commit()
            return {
                "workspace_id": workspace_id,
                "methodology_version": "temporal-claims-v1",
                "identity_count": len(report_identities),
                "claim_count": len(rows),
                "relation_count": len(relation_tuples),
                "integrity_hash": integrity,
                "identities": report_identities,
            }

    async def claim_timeline(self, claim_id: str) -> dict:
        async with self._session_factory() as session:
            claim = await session.get(AnalyticClaimRecord, claim_id)
            if claim is None:
                raise LookupError("Claim не найден")
            if not claim.claim_identity_id:
                raise LookupError("Timeline ещё не построен")
            identity = await session.get(ClaimIdentityRecord, claim.claim_identity_id)
            rows = (await session.execute(
                select(AnalyticClaimRecord, ProvenanceBundleRecord)
                .join(ProvenanceBundleRecord, ProvenanceBundleRecord.id == AnalyticClaimRecord.bundle_id)
                .where(AnalyticClaimRecord.claim_identity_id == claim.claim_identity_id)
                .order_by(ProvenanceBundleRecord.created_at)
            )).all()
            links = (await session.execute(
                select(ClaimTimelineLinkRecord)
                .where(ClaimTimelineLinkRecord.claim_identity_id == claim.claim_identity_id)
                .order_by(ClaimTimelineLinkRecord.created_at)
            )).scalars().all()
            return {
                "claim_identity_id": claim.claim_identity_id,
                "workspace_id": identity.workspace_id if identity else None,
                "canonical_statement": identity.canonical_statement if identity else claim.statement,
                "claims": [{
                    "claim_id": item.id,
                    "generated_at": bundle.created_at.isoformat(),
                    "statement": item.statement,
                    "temporal_status": item.temporal_status,
                    "review_status": item.review_status,
                } for item, bundle in rows],
                "relations": [{
                    "source_claim_id": link.source_claim_id,
                    "target_claim_id": link.target_claim_id,
                    "relation_type": link.relation_type,
                    "confidence": link.confidence,
                    "rationale": link.rationale_json,
                    "event_hash": link.event_hash,
                } for link in links],
            }
