from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.models import WorkspaceItemRecord, WorkspaceRecord
from app.workspaces.models import Workspace, WorkspaceItem, WorkspaceItemType
from app.workspaces.service import normalize_item, normalize_workspace_name


class WorkspaceRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _map(record: WorkspaceRecord) -> Workspace:
        return Workspace(record.id, record.telegram_user_id, record.name, record.description, record.is_active,
            tuple(WorkspaceItem(i.id, WorkspaceItemType(i.item_type), i.value, i.normalized_value,
                i.label, i.metadata_json or {}, i.created_at) for i in sorted(record.items, key=lambda x: (x.item_type, x.normalized_value))),
            record.created_at, record.updated_at)

    async def create(self, user_id: int, name: str, description: str | None = None) -> Workspace:
        clean = normalize_workspace_name(name)
        async with self._session_factory() as session:
            existing = (await session.execute(select(WorkspaceRecord).where(
                WorkspaceRecord.telegram_user_id == user_id, WorkspaceRecord.name_key == clean.casefold()))).scalar_one_or_none()
            if existing:
                raise ValueError("Workspace с таким названием уже существует")
            record = WorkspaceRecord(telegram_user_id=user_id, name=clean, name_key=clean.casefold(), description=description)
            session.add(record); await session.commit(); await session.refresh(record)
            return self._map(record)

    async def list(self, user_id: int) -> list[Workspace]:
        query = select(WorkspaceRecord).options(selectinload(WorkspaceRecord.items)).where(
            WorkspaceRecord.telegram_user_id == user_id, WorkspaceRecord.is_active.is_(True)).order_by(WorkspaceRecord.created_at)
        async with self._session_factory() as session:
            return [self._map(r) for r in (await session.execute(query)).scalars().unique().all()]

    async def list_for_channel(self, user_id: int, channel_username: str) -> list[Workspace]:
        normalized = channel_username.strip().casefold().lstrip("@")
        query = (
            select(WorkspaceRecord)
            .options(selectinload(WorkspaceRecord.items))
            .join(WorkspaceItemRecord, WorkspaceItemRecord.workspace_id == WorkspaceRecord.id)
            .where(
                WorkspaceRecord.telegram_user_id == user_id,
                WorkspaceRecord.is_active.is_(True),
                WorkspaceItemRecord.item_type == WorkspaceItemType.CHANNEL.value,
                WorkspaceItemRecord.normalized_value == normalized,
            )
            .order_by(WorkspaceRecord.created_at)
        )
        async with self._session_factory() as session:
            records = (await session.execute(query)).scalars().unique().all()
            return [self._map(record) for record in records]

    async def get(self, user_id: int, workspace_id: str) -> Workspace | None:
        query = select(WorkspaceRecord).options(selectinload(WorkspaceRecord.items)).where(
            WorkspaceRecord.telegram_user_id == user_id, WorkspaceRecord.id == workspace_id)
        async with self._session_factory() as session:
            record = (await session.execute(query)).scalar_one_or_none()
            return self._map(record) if record else None

    async def add_item(self, user_id: int, workspace_id: str, item_type: WorkspaceItemType, value: str, label: str | None = None) -> Workspace:
        normalized = normalize_item(item_type, value)
        async with self._session_factory() as session:
            workspace = (await session.execute(select(WorkspaceRecord).options(selectinload(WorkspaceRecord.items)).where(
                WorkspaceRecord.id == workspace_id, WorkspaceRecord.telegram_user_id == user_id))).scalar_one_or_none()
            if workspace is None: raise LookupError("Workspace не найден")
            if any(i.item_type == item_type.value and i.normalized_value == normalized for i in workspace.items):
                raise ValueError("Объект уже добавлен в Workspace")
            session.add(WorkspaceItemRecord(workspace_id=workspace.id, item_type=item_type.value, value=value.strip(), normalized_value=normalized, label=label, metadata_json={}))
            await session.commit()
        result = await self.get(user_id, workspace_id)
        assert result is not None
        return result

    async def remove_item(self, user_id: int, workspace_id: str, item_type: WorkspaceItemType, value: str) -> bool:
        normalized = normalize_item(item_type, value)
        async with self._session_factory() as session:
            workspace = (await session.execute(select(WorkspaceRecord.id).where(WorkspaceRecord.id == workspace_id, WorkspaceRecord.telegram_user_id == user_id))).scalar_one_or_none()
            if workspace is None: return False
            result = await session.execute(delete(WorkspaceItemRecord).where(WorkspaceItemRecord.workspace_id == workspace_id,
                WorkspaceItemRecord.item_type == item_type.value, WorkspaceItemRecord.normalized_value == normalized))
            await session.commit(); return bool(result.rowcount)

    async def delete(self, user_id: int, workspace_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(WorkspaceRecord).where(WorkspaceRecord.id == workspace_id, WorkspaceRecord.telegram_user_id == user_id))
            await session.commit(); return bool(result.rowcount)
