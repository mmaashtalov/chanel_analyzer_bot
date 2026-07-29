from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticClaimRecord,
    ClaimContradictionEventRecord,
    ClaimContradictionRecord,
    ClaimIdentityRecord,
    ProvenanceBundleRecord,
)
from app.db.temporal_claim_repository import (
    CONTRADICTION_METHODOLOGY,
    TEMPORAL_METHODOLOGY,
    TemporalClaimRepository,
)
from app.evidence.contradictions import (
    ACTION_STATUS,
    ContradictionResolutionAction,
    ContradictionStatus,
    event_hash,
    resolution_history_integrity,
    severity_rank,
    triage_priority,
    validate_resolution,
)
from app.evidence.review import recalculate_integrity


class ContradictionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_queue(
        self,
        workspace_id: str,
        status_filter: str = "open",
        limit: int = 20,
        *,
        include_history: bool = False,
    ) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("limit должен быть от 1 до 50")
        statuses = _status_filter(status_filter)
        async with self._session_factory() as session:
            query = select(ClaimContradictionRecord).where(
                ClaimContradictionRecord.workspace_id == workspace_id,
                ClaimContradictionRecord.active.is_(True),
            )
            if statuses is not None:
                query = query.where(ClaimContradictionRecord.status.in_(statuses))
            rows = (await session.execute(query)).scalars().all()
            mapped = [
                await self._map(session, row, include_history=include_history)
                for row in rows
            ]
            mapped.sort(
                key=lambda item: (
                    triage_priority(item["severity"], item["confidence"]),
                    severity_rank(item["severity"]),
                    item["confidence"],
                    item["created_at"],
                ),
                reverse=True,
            )
            return mapped[:limit]

    async def get(self, contradiction_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.get(ClaimContradictionRecord, contradiction_id)
            return None if row is None else await self._map(session, row, include_history=True)

    async def context(self, contradiction_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.get(ClaimContradictionRecord, contradiction_id)
            if row is None:
                return None
            return {
                "contradiction_id": row.id,
                "workspace_id": row.workspace_id,
                "claim_identity_id": row.claim_identity_id,
                "source_claim_id": row.source_claim_id,
                "target_claim_id": row.target_claim_id,
                "status": row.status,
                "active": row.active,
            }

    async def history(self, contradiction_id: str) -> list[dict]:
        async with self._session_factory() as session:
            events = await self._events(session, contradiction_id)
            return [_map_event(item) for item in events]

    async def resolve(
        self,
        contradiction_id: str,
        telegram_user_id: int,
        action: ContradictionResolutionAction,
        selected_claim_id: str | None = None,
        comment: str | None = None,
        details: dict | None = None,
    ) -> dict:
        async with self._session_factory() as session:
            row = await session.get(ClaimContradictionRecord, contradiction_id)
            if row is None or not row.active:
                raise LookupError("Contradiction не найден в активной очереди")
            validate_resolution(
                action,
                row.source_claim_id,
                row.target_claim_id,
                selected_claim_id,
            )
            source_bundle, target_bundle = await self._claim_bundles(session, row)
            if action is ContradictionResolutionAction.ACCEPT_NEWER:
                selected_claim_id = self._newer_claim_id(
                    row.source_claim_id,
                    row.target_claim_id,
                    source_bundle.created_at,
                    target_bundle.created_at,
                    selected_claim_id,
                )
            new_status = ACTION_STATUS[action]
            if (
                row.status == new_status.value
                and row.resolution_action == action.value
                and row.selected_claim_id == selected_claim_id
                and (row.resolution_comment or "") == (comment or "")
            ):
                raise ValueError("Это решение уже применено к contradiction")

            previous_event = (await session.execute(
                select(ClaimContradictionEventRecord)
                .where(ClaimContradictionEventRecord.contradiction_id == contradiction_id)
                .order_by(ClaimContradictionEventRecord.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            now = datetime.now(UTC)
            previous_event_hash = previous_event.event_hash if previous_event else None
            current_event_hash = event_hash(
                contradiction_id=contradiction_id,
                telegram_user_id=telegram_user_id,
                previous_status=row.status,
                action=action.value,
                new_status=new_status.value,
                selected_claim_id=selected_claim_id,
                comment=comment,
                previous_event_hash=previous_event_hash,
                created_at=now.isoformat(),
            )
            event_details = dict(details or {})
            event_details.update({
                "source_claim_id": row.source_claim_id,
                "target_claim_id": row.target_claim_id,
                "triage_priority": triage_priority(row.severity, row.confidence),
            })
            session.add(ClaimContradictionEventRecord(
                contradiction_id=contradiction_id,
                telegram_user_id=telegram_user_id,
                previous_status=row.status,
                action=action.value,
                new_status=new_status.value,
                selected_claim_id=selected_claim_id,
                comment=comment,
                details_json=event_details,
                previous_event_hash=previous_event_hash,
                event_hash=current_event_hash,
                created_at=now,
            ))
            row.status = new_status.value
            row.resolution_action = action.value
            row.selected_claim_id = selected_claim_id
            row.resolution_comment = comment
            row.resolved_by = telegram_user_id
            row.resolved_at = now
            row.updated_at = now
            await self._sync_identity_projection(session, row.claim_identity_id)
            await session.commit()
            result = await self._map(session, row, include_history=True)
            result["last_event_hash"] = current_event_hash
            return result

    async def dossier(self, workspace_id: str, status_filter: str = "all") -> dict:
        contradictions = await self.list_queue(
            workspace_id,
            status_filter,
            limit=50,
            include_history=True,
        )
        canonical = "|".join(
            f"{item['contradiction_id']}|{item['status']}|{item.get('last_event_hash') or ''}"
            for item in contradictions
        )
        return {
            "workspace_id": workspace_id,
            "methodology_version": CONTRADICTION_METHODOLOGY,
            "status_filter": status_filter,
            "contradiction_count": len(contradictions),
            "unresolved_count": sum(
                item["status"] in {
                    ContradictionStatus.OPEN.value,
                    ContradictionStatus.NEEDS_EVIDENCE.value,
                }
                for item in contradictions
            ),
            "integrity_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "contradictions": contradictions,
        }

    async def _map(
        self,
        session: AsyncSession,
        row: ClaimContradictionRecord,
        *,
        include_history: bool = False,
    ) -> dict:
        source = await session.get(AnalyticClaimRecord, row.source_claim_id)
        target = await session.get(AnalyticClaimRecord, row.target_claim_id)
        source_bundle = await session.get(
            ProvenanceBundleRecord, source.bundle_id
        ) if source else None
        target_bundle = await session.get(
            ProvenanceBundleRecord, target.bundle_id
        ) if target else None
        result = {
            "contradiction_id": row.id,
            "workspace_id": row.workspace_id,
            "claim_identity_id": row.claim_identity_id,
            "source_claim_id": row.source_claim_id,
            "target_claim_id": row.target_claim_id,
            "source_statement": source.statement if source else None,
            "target_statement": target.statement if target else None,
            "source_assessment": source.assessment if source else None,
            "target_assessment": target.assessment if target else None,
            "source_generated_at": source_bundle.created_at.isoformat() if source_bundle else None,
            "target_generated_at": target_bundle.created_at.isoformat() if target_bundle else None,
            "severity": row.severity,
            "confidence": row.confidence,
            "triage_priority": triage_priority(row.severity, row.confidence),
            "rationale": row.rationale_json,
            "status": row.status,
            "resolution_action": row.resolution_action,
            "selected_claim_id": row.selected_claim_id,
            "resolution_comment": row.resolution_comment,
            "resolved_by": row.resolved_by,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "active": row.active,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        if include_history:
            history = [_map_event(item) for item in await self._events(session, row.id)]
            result["history"] = history
            result["history_integrity"] = resolution_history_integrity(history)
            result["last_event_hash"] = history[-1]["event_hash"] if history else None
        return result

    @staticmethod
    async def _events(
        session: AsyncSession,
        contradiction_id: str,
    ) -> list[ClaimContradictionEventRecord]:
        return list((await session.execute(
            select(ClaimContradictionEventRecord)
            .where(ClaimContradictionEventRecord.contradiction_id == contradiction_id)
            .order_by(ClaimContradictionEventRecord.created_at.asc())
        )).scalars().all())

    @staticmethod
    async def _claim_bundles(
        session: AsyncSession,
        row: ClaimContradictionRecord,
    ) -> tuple[ProvenanceBundleRecord, ProvenanceBundleRecord]:
        source = await session.get(AnalyticClaimRecord, row.source_claim_id)
        target = await session.get(AnalyticClaimRecord, row.target_claim_id)
        if source is None or target is None:
            raise LookupError("Claims contradiction не найдены")
        source_bundle = await session.get(ProvenanceBundleRecord, source.bundle_id)
        target_bundle = await session.get(ProvenanceBundleRecord, target.bundle_id)
        if source_bundle is None or target_bundle is None:
            raise LookupError("Provenance bundle contradiction не найден")
        return source_bundle, target_bundle

    @staticmethod
    def _newer_claim_id(
        source_claim_id: str,
        target_claim_id: str,
        source_generated_at: datetime,
        target_generated_at: datetime,
        selected_claim_id: str | None,
    ) -> str:
        newer = target_claim_id if target_generated_at > source_generated_at else source_claim_id
        if target_generated_at == source_generated_at:
            raise ValueError("Нельзя определить newer claim: даты наблюдений совпадают")
        if selected_claim_id != newer:
            raise ValueError("Для action newer нужно выбрать более новый claim")
        return newer

    async def _sync_identity_projection(self, session: AsyncSession, claim_identity_id: str) -> None:
        identity = await session.get(ClaimIdentityRecord, claim_identity_id)
        if identity is None:
            raise LookupError("Claim identity не найдена")
        rows = (await session.execute(
            select(AnalyticClaimRecord, ProvenanceBundleRecord)
            .join(ProvenanceBundleRecord, ProvenanceBundleRecord.id == AnalyticClaimRecord.bundle_id)
            .where(AnalyticClaimRecord.claim_identity_id == claim_identity_id)
            .order_by(ProvenanceBundleRecord.created_at, AnalyticClaimRecord.claim_index)
        )).all()
        contradictions = list((await session.execute(
            select(ClaimContradictionRecord)
            .where(
                ClaimContradictionRecord.claim_identity_id == claim_identity_id,
                ClaimContradictionRecord.active.is_(True),
            )
        )).scalars().all())
        TemporalClaimRepository._apply_identity_projection(identity, list(rows), contradictions)
        contradiction_by_claim: dict[str, list[ClaimContradictionRecord]] = {}
        for contradiction in contradictions:
            contradiction_by_claim.setdefault(contradiction.source_claim_id, []).append(contradiction)
            contradiction_by_claim.setdefault(contradiction.target_claim_id, []).append(contradiction)
        for claim, bundle in rows:
            payload = dict(bundle.bundle_json)
            for claim_payload in payload.get("claims", []):
                if str(claim_payload.get("claim_id")) != claim.id:
                    continue
                claim_payload["claim_identity_id"] = claim.claim_identity_id
                claim_payload["temporal_status"] = claim.temporal_status
                claim_payload["canonical_claim_id"] = identity.canonical_claim_id
                claim_payload["contradictions"] = [
                    {
                        "contradiction_id": item.id,
                        "status": item.status,
                        "resolution_action": item.resolution_action,
                    }
                    for item in contradiction_by_claim.get(claim.id, [])
                ]
            payload["methodology_version"] = (
                CONTRADICTION_METHODOLOGY if contradictions else TEMPORAL_METHODOLOGY
            )
            payload["integrity_hash"] = recalculate_integrity(payload)
            bundle.bundle_json = payload
            bundle.methodology_version = payload["methodology_version"]
            bundle.integrity_hash = payload["integrity_hash"]


def _status_filter(raw: str) -> set[str] | None:
    normalized = raw.strip().casefold()
    if normalized in {"all", "*"}:
        return None
    if normalized in {"open", "unresolved", "pending"}:
        return {ContradictionStatus.OPEN.value, ContradictionStatus.NEEDS_EVIDENCE.value}
    return {ContradictionStatus.parse(normalized).value}


def _map_event(row: ClaimContradictionEventRecord) -> dict:
    return {
        "id": row.id,
        "contradiction_id": row.contradiction_id,
        "telegram_user_id": row.telegram_user_id,
        "previous_status": row.previous_status,
        "action": row.action,
        "new_status": row.new_status,
        "selected_claim_id": row.selected_claim_id,
        "comment": row.comment,
        "details": row.details_json,
        "previous_event_hash": row.previous_event_hash,
        "event_hash": row.event_hash,
        "created_at": row.created_at.isoformat(),
    }
