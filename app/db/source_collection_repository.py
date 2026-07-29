from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import SourceDocumentRecord, SourceErrorRecord, SourceRecord, SourceRunRecord
from app.sources.base import SourceAdapter
from app.sources.models import UnifiedDocument


@dataclass(slots=True, frozen=True)
class CollectionStats:
    source_type: str
    source_id: str
    collected: int
    accepted: int
    duplicates: int


class SourceCollectionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def persist(
        self, adapter: SourceAdapter, source_external_id: str, documents: tuple[UnifiedDocument, ...]
    ) -> CollectionStats:
        async with self._session_factory() as session:
            source = await self._get_or_create_source(session, adapter, source_external_id)
            run = SourceRunRecord(source_id=source.id, status="running")
            session.add(run)
            await session.flush()
            accepted = 0
            duplicates = 0
            for document in documents:
                existing = (await session.execute(
                    select(SourceDocumentRecord.id).where(or_(
                        SourceDocumentRecord.fingerprint == document.fingerprint,
                        (SourceDocumentRecord.source_id == source.id)
                        & (SourceDocumentRecord.external_document_id == document.document_id),
                    )).limit(1)
                )).scalar_one_or_none()
                if existing is not None:
                    duplicates += 1
                    continue
                session.add(SourceDocumentRecord(
                    source_id=source.id,
                    source_run_id=run.id,
                    external_document_id=document.document_id,
                    title=document.title,
                    body=document.body,
                    author=document.author,
                    language=document.language,
                    canonical_url=document.canonical_url,
                    published_at=document.published_at,
                    fingerprint=document.fingerprint,
                    content_fingerprint=document.content_fingerprint,
                    document_json=document.to_dict(),
                ))
                accepted += 1
            now = datetime.now(UTC)
            run.status = "completed"
            run.collected_count = len(documents)
            run.accepted_count = accepted
            run.duplicate_count = duplicates
            run.finished_at = now
            source.last_success_at = now
            await session.commit()
            return CollectionStats(adapter.source_type.value, source_external_id, len(documents), accepted, duplicates)

    async def record_failure(
        self, adapter: SourceAdapter, source_external_id: str, error: Exception
    ) -> None:
        async with self._session_factory() as session:
            source = await self._get_or_create_source(session, adapter, source_external_id)
            now = datetime.now(UTC)
            run = SourceRunRecord(
                source_id=source.id, status="failed", finished_at=now, error_message=str(error)[:2000]
            )
            session.add(run)
            await session.flush()
            session.add(SourceErrorRecord(
                source_id=source.id,
                source_run_id=run.id,
                error_type=type(error).__name__,
                message=str(error)[:2000],
                details_json={"adapter": adapter.name, "version": adapter.version},
            ))
            source.last_error_at = now
            await session.commit()

    @staticmethod
    async def _get_or_create_source(
        session: AsyncSession, adapter: SourceAdapter, source_external_id: str
    ) -> SourceRecord:
        source = (await session.execute(select(SourceRecord).where(
            SourceRecord.source_type == adapter.source_type.value,
            SourceRecord.external_id == source_external_id,
        ))).scalar_one_or_none()
        if source is None:
            source = SourceRecord(
                source_type=adapter.source_type.value,
                external_id=source_external_id,
                display_name=source_external_id,
                adapter_name=adapter.name,
                adapter_version=adapter.version,
                metadata_json={},
            )
            session.add(source)
            await session.flush()
        else:
            source.adapter_name = adapter.name
            source.adapter_version = adapter.version
        return source
