from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import SourceDocumentRecord, SourceRecord, WorkspaceItemRecord
from app.evidence.document_linker import SourceDocumentEvidence


class DocumentEvidenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_for_workspace(
        self,
        workspace_id: str,
        published_from: datetime,
        published_to: datetime,
        limit: int = 500,
    ) -> tuple[SourceDocumentEvidence, ...]:
        item_query = select(WorkspaceItemRecord).where(
            WorkspaceItemRecord.workspace_id == workspace_id,
            WorkspaceItemRecord.item_type.in_(("channel", "rss", "domain")),
        )
        async with self._session_factory() as session:
            items = tuple((await session.execute(item_query)).scalars().all())
            if not items:
                return ()
            values = {item.normalized_value.casefold().lstrip("@") for item in items}
            source_filters = []
            for value in values:
                source_filters.extend((
                    SourceRecord.external_id.ilike(f"%{value}%"),
                    SourceRecord.display_name.ilike(f"%{value}%"),
                ))
            query = (
                select(SourceDocumentRecord, SourceRecord)
                .join(SourceRecord, SourceDocumentRecord.source_id == SourceRecord.id)
                .where(
                    SourceDocumentRecord.published_at >= published_from,
                    SourceDocumentRecord.published_at <= published_to,
                    or_(*source_filters),
                )
                .order_by(SourceDocumentRecord.published_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(query)).all()
        return tuple(
            SourceDocumentEvidence(
                document_id=document.id,
                source_id=source.id,
                source_type=source.source_type,
                source_external_id=source.external_id,
                title=document.title,
                body=document.body,
                author=document.author,
                canonical_url=document.canonical_url,
                published_at=document.published_at,
                fingerprint=document.fingerprint,
                content_fingerprint=document.content_fingerprint,
            )
            for document, source in rows
        )
