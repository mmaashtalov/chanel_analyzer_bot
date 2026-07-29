from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticClaimRecord,
    ClaimContradictionRecord,
    ClaimIdentityRecord,
    ClaimTimelineLinkRecord,
    ProvenanceBundleRecord,
    WorkspaceProvenanceLinkRecord,
)
from app.evidence.contradictions import (
    ContradictionStatus,
    normalize_severity,
    stable_contradiction_id,
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

TEMPORAL_METHODOLOGY = "temporal-claims-v1"
CONTRADICTION_METHODOLOGY = "contradiction-resolution-v1"


class TemporalClaimRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def build_workspace_timeline(self, workspace_id: str) -> dict:
        async with self._session_factory() as session:
            linked_bundle_ids = select(WorkspaceProvenanceLinkRecord.bundle_id).where(
                WorkspaceProvenanceLinkRecord.workspace_id == workspace_id
            )
            rows = (await session.execute(
                select(AnalyticClaimRecord, ProvenanceBundleRecord)
                .join(ProvenanceBundleRecord, ProvenanceBundleRecord.id == AnalyticClaimRecord.bundle_id)
                .where(or_(
                    ProvenanceBundleRecord.subject_id.like(f"{workspace_id}:%"),
                    ProvenanceBundleRecord.id.in_(linked_bundle_ids),
                ))
                .order_by(ProvenanceBundleRecord.created_at, AnalyticClaimRecord.claim_index)
            )).all()
            if not rows:
                raise LookupError("Для Workspace ещё нет claims")

            grouped: dict[str, list[tuple[AnalyticClaimRecord, ProvenanceBundleRecord]]] = {}
            for claim, bundle in rows:
                identity_id = stable_claim_identity(claim.category, claim.statement)
                grouped.setdefault(identity_id, []).append((claim, bundle))

            existing_contradictions = {
                row.id: row for row in (await session.execute(
                    select(ClaimContradictionRecord).where(
                        ClaimContradictionRecord.workspace_id == workspace_id
                    )
                )).scalars().all()
            }
            for contradiction in existing_contradictions.values():
                contradiction.active = False

            await session.execute(delete(ClaimTimelineLinkRecord).where(
                ClaimTimelineLinkRecord.workspace_id == workspace_id
            ))
            report_identities: list[dict] = []
            relation_tuples: list[tuple[str, str, str]] = []
            active_contradictions: list[ClaimContradictionRecord] = []

            for identity_id, items in grouped.items():
                identity = await session.get(ClaimIdentityRecord, identity_id)
                if identity is None:
                    first_claim = items[0][0]
                    identity = ClaimIdentityRecord(
                        id=identity_id,
                        workspace_id=workspace_id,
                        category=first_claim.category,
                        canonical_statement=first_claim.statement,
                        canonical_claim_id=first_claim.id,
                        methodology_version=TEMPORAL_METHODOLOGY,
                    )
                    session.add(identity)
                identity.updated_at = datetime.now(UTC)

                timeline: list[dict] = []
                previous_pair: tuple[AnalyticClaimRecord, ProvenanceBundleRecord] | None = None
                identity_contradictions: list[ClaimContradictionRecord] = []
                for claim, bundle in items:
                    claim.claim_identity_id = identity_id
                    claim.temporal_status = TemporalClaimStatus.CURRENT.value
                    relation_payload = None
                    if previous_pair is not None:
                        previous, previous_bundle = previous_pair
                        relation = classify_relation(
                            ClaimSnapshot(
                                previous.id,
                                previous.category,
                                previous.statement,
                                previous.assessment,
                                previous_bundle.created_at.isoformat(),
                                previous.confidence,
                            ),
                            ClaimSnapshot(
                                claim.id,
                                claim.category,
                                claim.statement,
                                claim.assessment,
                                bundle.created_at.isoformat(),
                                claim.confidence,
                            ),
                        )
                        event_hash = hashlib.sha256(
                            f"{previous.id}|{claim.id}|{relation.relation_type.value}|"
                            f"{relation.confidence:.6f}".encode()
                        ).hexdigest()
                        session.add(ClaimTimelineLinkRecord(
                            id=str(uuid.uuid4()),
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
                            contradiction_id = stable_contradiction_id(
                                workspace_id, identity_id, previous.id, claim.id
                            )
                            contradiction = existing_contradictions.get(contradiction_id)
                            relation_confidence = min(
                                1.0,
                                relation.confidence * 0.6
                                + ((previous.confidence + claim.confidence) / 2) * 0.4,
                            )
                            if contradiction is None:
                                contradiction = ClaimContradictionRecord(
                                    id=contradiction_id,
                                    workspace_id=workspace_id,
                                    claim_identity_id=identity_id,
                                    source_claim_id=previous.id,
                                    target_claim_id=claim.id,
                                    severity=normalize_severity(
                                        _highest_severity(previous.severity, claim.severity)
                                    ),
                                    confidence=round(relation_confidence, 6),
                                    rationale_json=list(relation.rationale),
                                    status=ContradictionStatus.OPEN.value,
                                    active=True,
                                )
                                session.add(contradiction)
                                existing_contradictions[contradiction_id] = contradiction
                            else:
                                contradiction.severity = normalize_severity(
                                    _highest_severity(previous.severity, claim.severity)
                                )
                                contradiction.confidence = round(relation_confidence, 6)
                                contradiction.rationale_json = list(relation.rationale)
                                contradiction.active = True
                                contradiction.updated_at = datetime.now(UTC)
                            identity_contradictions.append(contradiction)
                            active_contradictions.append(contradiction)
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

                self._apply_identity_projection(identity, items, identity_contradictions)
                for item in timeline:
                    claim = next(record for record, _ in items if record.id == item["claim_id"])
                    item["temporal_status"] = claim.temporal_status
                report_identities.append({
                    "claim_identity_id": identity_id,
                    "category": identity.category,
                    "canonical_claim_id": identity.canonical_claim_id,
                    "canonical_statement": identity.canonical_statement,
                    "canonical_status": (
                        "current" if identity.canonical_claim_id else "unresolved"
                    ),
                    "timeline": timeline,
                })

            await session.flush()
            # Embed temporal and contradiction metadata in every affected bundle.
            bundle_map: dict[str, ProvenanceBundleRecord] = {bundle.id: bundle for _, bundle in rows}
            claim_map = {claim.id: claim for claim, _ in rows}
            identity_map = {
                identity_id: await session.get(ClaimIdentityRecord, identity_id)
                for identity_id in grouped
            }
            claim_contradictions: dict[str, list[ClaimContradictionRecord]] = {}
            for contradiction in active_contradictions:
                claim_contradictions.setdefault(contradiction.source_claim_id, []).append(contradiction)
                claim_contradictions.setdefault(contradiction.target_claim_id, []).append(contradiction)
            for bundle in bundle_map.values():
                payload = dict(bundle.bundle_json)
                for claim_payload in payload.get("claims", []):
                    record = claim_map.get(str(claim_payload.get("claim_id")))
                    if record is None:
                        continue
                    identity = identity_map.get(record.claim_identity_id)
                    claim_payload["claim_identity_id"] = record.claim_identity_id
                    claim_payload["temporal_status"] = record.temporal_status
                    claim_payload["canonical_claim_id"] = (
                        identity.canonical_claim_id if identity else None
                    )
                    claim_payload["contradictions"] = [
                        {
                            "contradiction_id": item.id,
                            "status": item.status,
                            "resolution_action": item.resolution_action,
                        }
                        for item in claim_contradictions.get(record.id, [])
                        if item.active
                    ]
                payload["methodology_version"] = (
                    CONTRADICTION_METHODOLOGY if active_contradictions else TEMPORAL_METHODOLOGY
                )
                payload["integrity_hash"] = recalculate_integrity(payload)
                bundle.bundle_json = payload
                bundle.methodology_version = payload["methodology_version"]
                bundle.integrity_hash = payload["integrity_hash"]

            integrity = timeline_integrity(
                (claim.id for claim, _ in rows),
                relation_tuples,
            )
            await session.commit()
            active_unique = {item.id: item for item in active_contradictions}
            return {
                "workspace_id": workspace_id,
                "methodology_version": (
                    CONTRADICTION_METHODOLOGY if active_unique else TEMPORAL_METHODOLOGY
                ),
                "identity_count": len(report_identities),
                "claim_count": len(rows),
                "relation_count": len(relation_tuples),
                "contradiction_count": len(active_unique),
                "unresolved_contradiction_count": sum(
                    item.status in {
                        ContradictionStatus.OPEN.value,
                        ContradictionStatus.NEEDS_EVIDENCE.value,
                    }
                    for item in active_unique.values()
                ),
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
            contradictions = (await session.execute(
                select(ClaimContradictionRecord)
                .where(
                    ClaimContradictionRecord.claim_identity_id == claim.claim_identity_id,
                    ClaimContradictionRecord.active.is_(True),
                )
                .order_by(ClaimContradictionRecord.created_at)
            )).scalars().all()
            return {
                "claim_identity_id": claim.claim_identity_id,
                "workspace_id": identity.workspace_id if identity else None,
                "canonical_claim_id": identity.canonical_claim_id if identity else None,
                "canonical_statement": identity.canonical_statement if identity else claim.statement,
                "canonical_status": "current" if identity and identity.canonical_claim_id else "unresolved",
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
                "contradictions": [{
                    "contradiction_id": item.id,
                    "source_claim_id": item.source_claim_id,
                    "target_claim_id": item.target_claim_id,
                    "severity": item.severity,
                    "confidence": item.confidence,
                    "status": item.status,
                    "resolution_action": item.resolution_action,
                    "selected_claim_id": item.selected_claim_id,
                } for item in contradictions],
            }

    @staticmethod
    def _apply_identity_projection(
        identity: ClaimIdentityRecord,
        items: list[tuple[AnalyticClaimRecord, ProvenanceBundleRecord]],
        contradictions: list[ClaimContradictionRecord],
    ) -> None:
        latest_claim = items[-1][0]
        identity.canonical_claim_id = latest_claim.id
        identity.canonical_statement = latest_claim.statement
        unresolved = False
        for contradiction in contradictions:
            source = next(item for item, _ in items if item.id == contradiction.source_claim_id)
            target = next(item for item, _ in items if item.id == contradiction.target_claim_id)
            if contradiction.status in {
                ContradictionStatus.OPEN.value,
                ContradictionStatus.CONFIRMED.value,
                ContradictionStatus.NEEDS_EVIDENCE.value,
            }:
                source.temporal_status = TemporalClaimStatus.CONTRADICTED.value
                target.temporal_status = TemporalClaimStatus.CONTRADICTED.value
                unresolved = True
            elif contradiction.status == ContradictionStatus.COMPATIBLE.value:
                source.temporal_status = TemporalClaimStatus.CURRENT.value
                target.temporal_status = TemporalClaimStatus.CURRENT.value
            elif contradiction.status == ContradictionStatus.RESOLVED_BY_NEWER.value:
                selected_id = contradiction.selected_claim_id or target.id
                selected = source if source.id == selected_id else target
                other = target if selected is source else source
                selected.temporal_status = TemporalClaimStatus.CURRENT.value
                other.temporal_status = TemporalClaimStatus.SUPERSEDED.value
                identity.canonical_claim_id = selected.id
                identity.canonical_statement = selected.statement
        if unresolved:
            identity.canonical_claim_id = None
        identity.methodology_version = (
            CONTRADICTION_METHODOLOGY if contradictions else TEMPORAL_METHODOLOGY
        )


def _highest_severity(left: str, right: str) -> str:
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    return max((left, right), key=lambda value: order.get(str(value).casefold(), 2))
