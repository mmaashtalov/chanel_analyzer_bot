from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticClaimRecord,
    ClaimReviewEventRecord,
    ProvenanceBundleRecord,
    WorkspaceProvenanceLinkRecord,
)
from app.evidence.review import (
    ClaimReviewStatus,
    adjusted_scores,
    recalculate_integrity,
    review_completeness,
)


class ClaimReviewRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def latest_bundle_for_workspace(self, workspace_id: str) -> dict | None:
        linked_bundle_ids = select(WorkspaceProvenanceLinkRecord.bundle_id).where(
            WorkspaceProvenanceLinkRecord.workspace_id == workspace_id
        )
        query = (
            select(ProvenanceBundleRecord)
            .where(or_(
                ProvenanceBundleRecord.subject_id.like(f"{workspace_id}:%"),
                ProvenanceBundleRecord.id.in_(linked_bundle_ids),
            ))
            .order_by(ProvenanceBundleRecord.created_at.desc())
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).scalar_one_or_none()
            return None if row is None else row.bundle_json

    async def claim_context(self, claim_id: str) -> dict | None:
        query = (
            select(AnalyticClaimRecord, ProvenanceBundleRecord)
            .join(ProvenanceBundleRecord, ProvenanceBundleRecord.id == AnalyticClaimRecord.bundle_id)
            .where(AnalyticClaimRecord.id == claim_id)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).first()
            if row is None:
                return None
            claim, bundle = row
            workspace_ids = (await session.execute(
                select(WorkspaceProvenanceLinkRecord.workspace_id).where(
                    WorkspaceProvenanceLinkRecord.bundle_id == bundle.id
                )
            )).scalars().all()
            return {
                "claim_id": claim.id,
                "bundle_id": bundle.id,
                "subject_type": bundle.subject_type,
                "subject_id": bundle.subject_id,
                "workspace_ids": list(workspace_ids),
                "review_status": claim.review_status,
            }

    async def review_claim(
        self,
        claim_id: str,
        telegram_user_id: int,
        status: ClaimReviewStatus,
        comment: str | None,
    ) -> dict:
        async with self._session_factory() as session:
            claim = await session.get(AnalyticClaimRecord, claim_id)
            if claim is None:
                raise LookupError("Claim не найден")
            bundle = await session.get(ProvenanceBundleRecord, claim.bundle_id)
            if bundle is None:
                raise LookupError("Provenance bundle не найден")

            previous_status = claim.review_status
            claim.review_status = status.value
            claim.reviewed_by = telegram_user_id
            claim.reviewed_at = datetime.now(UTC)
            claim.review_comment = comment
            claim.review_version += 1
            claim.confidence, claim.evidence_quality = adjusted_scores(
                claim.confidence, claim.evidence_quality, status
            )

            payload = dict(bundle.bundle_json)
            claims = [dict(item) for item in payload.get("claims", [])]
            for item in claims:
                if item.get("claim_id") == claim_id:
                    item.update({
                        "review_status": status.value,
                        "reviewed_by": telegram_user_id,
                        "reviewed_at": claim.reviewed_at.isoformat(),
                        "review_comment": comment,
                        "review_version": claim.review_version,
                        "confidence": claim.confidence,
                        "evidence_quality": claim.evidence_quality,
                    })
                    break
            payload["claims"] = claims
            payload["review_completeness"] = review_completeness(claims)
            payload["integrity_hash"] = recalculate_integrity(payload)
            payload["methodology_version"] = "analyst-verification-v1"
            bundle.bundle_json = payload
            bundle.review_completeness = payload["review_completeness"]
            bundle.integrity_hash = payload["integrity_hash"]
            bundle.methodology_version = payload["methodology_version"]

            raw_event = (
                f"{claim_id}|{telegram_user_id}|{previous_status}|{status.value}|"
                f"{claim.review_version}|{comment or ''}"
            )
            session.add(ClaimReviewEventRecord(
                claim_id=claim_id,
                bundle_id=claim.bundle_id,
                telegram_user_id=telegram_user_id,
                previous_status=previous_status,
                new_status=status.value,
                comment=comment,
                event_hash=hashlib.sha256(raw_event.encode("utf-8")).hexdigest(),
            ))
            await session.commit()
            return payload

    async def history(self, claim_id: str) -> list[dict]:
        query = (
            select(ClaimReviewEventRecord)
            .where(ClaimReviewEventRecord.claim_id == claim_id)
            .order_by(ClaimReviewEventRecord.created_at.asc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(query)).scalars().all()
            return [
                {
                    "id": row.id,
                    "claim_id": row.claim_id,
                    "telegram_user_id": row.telegram_user_id,
                    "previous_status": row.previous_status,
                    "new_status": row.new_status,
                    "comment": row.comment,
                    "event_hash": row.event_hash,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
