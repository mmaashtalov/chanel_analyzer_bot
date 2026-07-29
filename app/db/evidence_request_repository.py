from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from dataclasses import asdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import EvidenceRequestEventRecord, EvidenceRequestRecord
from app.evidence.acquisition import EvidenceRequestPlan, EvidenceRequestStatus


class EvidenceRequestRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, workspace_id: str, telegram_user_id: int, plan: EvidenceRequestPlan, max_attempts: int = 3) -> dict:
        async with self._session_factory() as session:
            existing = (await session.execute(select(EvidenceRequestRecord).where(
                EvidenceRequestRecord.claim_id == plan.claim_id,
                EvidenceRequestRecord.status.in_(("queued", "retry_wait", "collecting", "linking")),
            ))).scalar_one_or_none()
            if existing is not None:
                return self._map(existing)
            row = EvidenceRequestRecord(
                workspace_id=workspace_id,
                claim_id=plan.claim_id,
                telegram_user_id=telegram_user_id,
                status=EvidenceRequestStatus.QUEUED.value,
                priority=plan.priority,
                gap_codes_json=list(plan.gap_codes),
                query_terms_json=list(plan.query_terms),
                source_plan_json=[asdict(item) for item in plan.sources],
                max_attempts=max_attempts,
            )
            session.add(row)
            await session.flush()
            self._add_event(session, row.id, None, row.status, {"gap_codes": row.gap_codes_json})
            await session.commit(); await session.refresh(row)
            return self._map(row)

    async def get_owned(self, request_id: str, telegram_user_id: int) -> dict | None:
        async with self._session_factory() as session:
            row = (await session.execute(select(EvidenceRequestRecord).where(
                EvidenceRequestRecord.id == request_id,
                EvidenceRequestRecord.telegram_user_id == telegram_user_id,
            ))).scalar_one_or_none()
            return None if row is None else self._map(row)

    async def get(self, request_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.get(EvidenceRequestRecord, request_id)
            return None if row is None else self._map(row)

    async def list_due(self, limit: int = 10) -> list[dict]:
        now = datetime.now(UTC)
        query = (
            select(EvidenceRequestRecord)
            .where(
                (EvidenceRequestRecord.status == EvidenceRequestStatus.QUEUED.value)
                | (
                    (EvidenceRequestRecord.status == EvidenceRequestStatus.RETRY_WAIT.value)
                    & (EvidenceRequestRecord.next_attempt_at <= now)
                )
            )
            .order_by(EvidenceRequestRecord.priority.desc(), EvidenceRequestRecord.requested_at)
            .limit(limit)
        )
        async with self._session_factory() as session:
            return [self._map(row) for row in (await session.execute(query)).scalars().all()]

    async def list_owned(self, telegram_user_id: int, workspace_id: str | None = None, limit: int = 20) -> list[dict]:
        query = select(EvidenceRequestRecord).where(EvidenceRequestRecord.telegram_user_id == telegram_user_id)
        if workspace_id:
            query = query.where(EvidenceRequestRecord.workspace_id == workspace_id)
        query = query.order_by(EvidenceRequestRecord.requested_at.desc()).limit(limit)
        async with self._session_factory() as session:
            return [self._map(row) for row in (await session.execute(query)).scalars().all()]

    async def transition(self, request_id: str, new_status: EvidenceRequestStatus, *, details: dict | None = None,
                         documents_collected: int | None = None, documents_linked: int | None = None,
                         error: str | None = None, increment_attempt: bool = False) -> dict:
        async with self._session_factory() as session:
            row = await session.get(EvidenceRequestRecord, request_id)
            if row is None: raise LookupError("Evidence request не найден")
            previous = row.status
            row.status = new_status.value
            row.updated_at = datetime.now(UTC)
            if increment_attempt:
                row.attempts += 1
                row.started_at = row.started_at or datetime.now(UTC)
                row.last_attempt_at = datetime.now(UTC)
            if documents_collected is not None:
                row.documents_collected = documents_collected
            if documents_linked is not None:
                row.documents_linked = documents_linked
            if error is not None:
                row.last_error = error
            terminal = {
                EvidenceRequestStatus.RESOLVED, EvidenceRequestStatus.PARTIAL,
                EvidenceRequestStatus.FAILED, EvidenceRequestStatus.CANCELLED,
            }
            if new_status in terminal:
                row.finished_at = datetime.now(UTC)
            else:
                row.finished_at = None
            self._add_event(session, row.id, previous, row.status, details or {})
            await session.commit(); await session.refresh(row)
            return self._map(row)

    async def history(self, request_id: str, telegram_user_id: int) -> list[dict]:
        owned = await self.get_owned(request_id, telegram_user_id)
        if owned is None: raise LookupError("Evidence request не найден")
        async with self._session_factory() as session:
            rows = (await session.execute(select(EvidenceRequestEventRecord).where(
                EvidenceRequestEventRecord.request_id == request_id
            ).order_by(EvidenceRequestEventRecord.created_at))).scalars().all()
            return [{"previous_status": r.previous_status, "new_status": r.new_status,
                     "details": r.details_json, "event_hash": r.event_hash,
                     "created_at": r.created_at.isoformat()} for r in rows]

    async def fulfill_from_store(self, request_id: str) -> dict:
        return await self.link_from_store(request_id, increment_attempt=True, stage="local_store")

    async def link_from_store(
        self, request_id: str, *, increment_attempt: bool, stage: str
    ) -> dict:
        """Link already collected source documents before any external retry.

        This is deliberately the first acquisition stage: it prevents repeated network
        collection when relevant primary material is already present in the local store.
        """
        from sqlalchemy import or_
        from app.db.models import (
            AnalyticClaimRecord, ClaimEvidenceLinkRecord, EvidenceReferenceRecord,
            ProvenanceBundleRecord, SourceDocumentRecord, SourceRecord,
        )
        from app.evidence.review import recalculate_integrity

        async with self._session_factory() as session:
            request = await session.get(EvidenceRequestRecord, request_id)
            if request is None:
                raise LookupError("Evidence request не найден")
            if increment_attempt and request.attempts >= request.max_attempts:
                raise ValueError("Достигнут лимит повторов")
            previous = request.status
            request.status = EvidenceRequestStatus.LINKING.value
            if increment_attempt:
                request.attempts += 1
                request.started_at = request.started_at or datetime.now(UTC)
                request.last_attempt_at = datetime.now(UTC)
            request.next_attempt_at = None
            self._add_event(session, request.id, previous, request.status, {"stage": stage})

            claim = await session.get(AnalyticClaimRecord, request.claim_id)
            if claim is None:
                raise LookupError("Claim не найден")
            bundle = await session.get(ProvenanceBundleRecord, claim.bundle_id)
            if bundle is None:
                raise LookupError("Provenance bundle не найден")

            terms = [str(term).casefold() for term in request.query_terms_json if str(term).strip()]
            filters = []
            for term in terms[:12]:
                filters.extend((SourceDocumentRecord.title.ilike(f"%{term}%"), SourceDocumentRecord.body.ilike(f"%{term}%")))
            if not filters:
                filters.append(SourceDocumentRecord.id == "__no_match__")
            source_ids = [str(item.get("source_id", "")).casefold().lstrip("@") for item in request.source_plan_json]
            source_filters = []
            for source_id in source_ids:
                source_filters.extend((SourceRecord.external_id.ilike(f"%{source_id}%"), SourceRecord.display_name.ilike(f"%{source_id}%")))

            query = select(SourceDocumentRecord, SourceRecord).join(
                SourceRecord, SourceDocumentRecord.source_id == SourceRecord.id
            ).where(or_(*filters))
            if source_filters:
                query = query.where(or_(*source_filters))
            rows = (await session.execute(query.order_by(SourceDocumentRecord.published_at.desc()).limit(20))).all()

            payload = dict(bundle.bundle_json)
            evidence_items = [dict(item) for item in payload.get("evidence", [])]
            claims = [dict(item) for item in payload.get("claims", [])]
            target = next((item for item in claims if item.get("claim_id") == claim.id), None)
            if target is None:
                raise LookupError("Claim отсутствует в bundle JSON")
            evidence_ids = list(target.get("evidence_ids", []))
            linked = 0
            source_types: set[str] = set()
            for document, source in rows:
                evidence_id = "evdoc_" + hashlib.sha256(f"{claim.id}:{document.id}".encode()).hexdigest()[:32]
                exists = await session.get(EvidenceReferenceRecord, evidence_id)
                excerpt = " ".join(document.body.split())[:420]
                item = {
                    "evidence_id": evidence_id, "kind": "primary_document", "source_id": source.id,
                    "locator": document.canonical_url or document.external_document_id,
                    "label": document.title or source.display_name or source.external_id,
                    "strength": "corroborating", "observed_at": document.created_at.isoformat(),
                    "value": {"source_external_id": source.external_id}, "content_hash": document.content_fingerprint,
                    "document_id": document.id, "source_type": source.source_type,
                    "canonical_url": document.canonical_url, "author": document.author,
                    "excerpt": excerpt, "published_at": document.published_at.isoformat(),
                    "fingerprint": document.fingerprint,
                }
                if exists is None:
                    session.add(EvidenceReferenceRecord(
                        id=evidence_id, bundle_id=bundle.id, kind="primary_document", source_id=source.id,
                        locator=item["locator"], label=item["label"], strength="corroborating",
                        observed_at=document.created_at, value_json=item["value"], content_hash=document.content_fingerprint,
                        document_id=document.id, source_type=source.source_type, canonical_url=document.canonical_url,
                        author=document.author, excerpt=excerpt, published_at=document.published_at, fingerprint=document.fingerprint,
                    ))
                    session.add(ClaimEvidenceLinkRecord(claim_id=claim.id, evidence_id=evidence_id))
                    evidence_items.append(item)
                    linked += 1
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
                source_types.add(source.source_type)

            target["evidence_ids"] = evidence_ids
            primary_count = len([item for item in evidence_items if item.get("evidence_id") in evidence_ids and item.get("kind") == "primary_document"])
            target["evidence_quality"] = min(1.0, float(target.get("evidence_quality", 0.0)) + 0.08 * linked)
            claim.evidence_quality = target["evidence_quality"]
            payload["claims"] = claims
            payload["evidence"] = evidence_items
            claims_with_primary = sum(1 for item in claims if any(
                ev.get("kind") == "primary_document" and ev.get("evidence_id") in item.get("evidence_ids", [])
                for ev in evidence_items
            ))
            payload["completeness"] = claims_with_primary / len(claims) if claims else 1.0
            payload["methodology_version"] = "evidence-acquisition-v1"
            payload["integrity_hash"] = recalculate_integrity(payload)
            bundle.bundle_json = payload
            bundle.completeness = payload["completeness"]
            bundle.methodology_version = payload["methodology_version"]
            bundle.integrity_hash = payload["integrity_hash"]

            request.documents_collected = max(request.documents_collected, len(rows))
            request.documents_linked += linked
            request.status = (EvidenceRequestStatus.RESOLVED.value if primary_count > 0 and len(source_types) >= 2
                              else EvidenceRequestStatus.PARTIAL.value if primary_count > 0
                              else EvidenceRequestStatus.FAILED.value)
            request.finished_at = datetime.now(UTC)
            request.last_error = None if primary_count else "Подходящие первичные документы в локальном хранилище не найдены"
            self._add_event(session, request.id, EvidenceRequestStatus.LINKING.value, request.status,
                            {"documents_found": len(rows), "documents_linked": linked, "source_types": sorted(source_types)})
            await session.commit(); await session.refresh(request)
            return self._map(request)


    async def count_local_candidates(self, request_id: str) -> int:
        from sqlalchemy import func, or_
        from app.db.models import SourceDocumentRecord, SourceRecord

        async with self._session_factory() as session:
            request = await session.get(EvidenceRequestRecord, request_id)
            if request is None:
                raise LookupError("Evidence request не найден")
            terms = [str(term).casefold() for term in request.query_terms_json if str(term).strip()]
            filters = []
            for term in terms[:12]:
                filters.extend((
                    SourceDocumentRecord.title.ilike(f"%{term}%"),
                    SourceDocumentRecord.body.ilike(f"%{term}%"),
                ))
            if not filters:
                return 0
            source_ids = [str(item.get("source_id", "")).casefold().lstrip("@") for item in request.source_plan_json]
            source_filters = []
            for source_id in source_ids:
                source_filters.extend((
                    SourceRecord.external_id.ilike(f"%{source_id}%"),
                    SourceRecord.display_name.ilike(f"%{source_id}%"),
                ))
            query = select(func.count(SourceDocumentRecord.id)).join(
                SourceRecord, SourceDocumentRecord.source_id == SourceRecord.id
            ).where(or_(*filters))
            if source_filters:
                query = query.where(or_(*source_filters))
            return int((await session.execute(query)).scalar_one() or 0)

    async def begin_collection(self, request_id: str) -> dict:
        async with self._session_factory() as session:
            row = await session.get(EvidenceRequestRecord, request_id)
            if row is None:
                raise LookupError("Evidence request не найден")
            if row.attempts >= row.max_attempts:
                raise ValueError("Достигнут лимит повторов")
            previous = row.status
            row.status = EvidenceRequestStatus.COLLECTING.value
            row.attempts += 1
            now = datetime.now(UTC)
            row.started_at = row.started_at or now
            row.last_attempt_at = now
            row.next_attempt_at = None
            row.finished_at = None
            row.last_error = None
            self._add_event(session, row.id, previous, row.status, {"stage": "external_collection"})
            await session.commit()
            await session.refresh(row)
            return self._map(row)

    async def record_collection(self, request_id: str, *, collected: int, summary: dict) -> dict:
        async with self._session_factory() as session:
            row = await session.get(EvidenceRequestRecord, request_id)
            if row is None:
                raise LookupError("Evidence request не найден")
            row.documents_collected += collected
            row.collection_summary_json = summary
            row.updated_at = datetime.now(UTC)
            self._add_event(session, row.id, row.status, row.status, {
                "stage": "collection_complete",
                "documents_collected": collected,
                "errors": len(summary.get("errors", [])),
            })
            await session.commit()
            await session.refresh(row)
            return self._map(row)

    async def schedule_retry(self, request_id: str, *, delay_seconds: int, error: str) -> dict:
        async with self._session_factory() as session:
            row = await session.get(EvidenceRequestRecord, request_id)
            if row is None:
                raise LookupError("Evidence request не найден")
            previous = row.status
            row.status = EvidenceRequestStatus.RETRY_WAIT.value
            row.next_attempt_at = datetime.now(UTC) + timedelta(seconds=max(30, delay_seconds))
            row.finished_at = None
            row.last_error = error
            self._add_event(session, row.id, previous, row.status, {
                "next_attempt_at": row.next_attempt_at.isoformat(),
                "error": error,
            })
            await session.commit()
            await session.refresh(row)
            return self._map(row)


    @staticmethod
    def _add_event(session: AsyncSession, request_id: str, previous: str | None, new: str, details: dict) -> None:
        raw = json.dumps({"request_id": request_id, "previous": previous, "new": new, "details": details,
                          "at": datetime.now(UTC).isoformat()}, ensure_ascii=False, sort_keys=True)
        session.add(EvidenceRequestEventRecord(request_id=request_id, previous_status=previous, new_status=new,
                                                details_json=details, event_hash=hashlib.sha256(raw.encode()).hexdigest()))

    @staticmethod
    def _map(row: EvidenceRequestRecord) -> dict:
        return {"id": row.id, "workspace_id": row.workspace_id, "claim_id": row.claim_id,
                "status": row.status, "priority": row.priority, "gap_codes": row.gap_codes_json,
                "query_terms": row.query_terms_json, "source_plan": row.source_plan_json,
                "attempts": row.attempts, "max_attempts": row.max_attempts,
                "documents_collected": row.documents_collected, "documents_linked": row.documents_linked,
                "last_error": row.last_error,
                "collection_summary": row.collection_summary_json,
                "requested_at": row.requested_at.isoformat(),
                "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
                "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None}
