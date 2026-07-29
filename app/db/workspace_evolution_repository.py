from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import WorkspaceEvolutionReportRecord, WorkspaceIntelligenceSnapshotRecord
from app.workspace_evolution.models import WorkspaceEvolutionReport


class WorkspaceEvolutionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def latest_pair(self, workspace_id: str, lookback_days: int = 30):
        query = (
            select(WorkspaceIntelligenceSnapshotRecord)
            .where(WorkspaceIntelligenceSnapshotRecord.workspace_id == workspace_id)
            .order_by(desc(WorkspaceIntelligenceSnapshotRecord.generated_at))
            .limit(2)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(query)).scalars().all())
        if len(rows) < 2:
            return None
        current, baseline = rows[0], rows[1]
        age_days = (current.generated_at - baseline.generated_at).total_seconds() / 86400
        if age_days > max(1, lookback_days):
            return None
        return baseline, current

    async def save(self, report: WorkspaceEvolutionReport, report_path: str | None = None) -> str:
        async with self._session_factory() as session:
            query = select(WorkspaceEvolutionReportRecord).where(
                WorkspaceEvolutionReportRecord.workspace_id == report.workspace_id,
                WorkspaceEvolutionReportRecord.baseline_snapshot_id == report.baseline_snapshot_id,
                WorkspaceEvolutionReportRecord.current_snapshot_id == report.current_snapshot_id,
            )
            record = (await session.execute(query)).scalar_one_or_none()
            if record is None:
                record = WorkspaceEvolutionReportRecord(
                    workspace_id=report.workspace_id,
                    baseline_snapshot_id=report.baseline_snapshot_id,
                    current_snapshot_id=report.current_snapshot_id,
                    baseline_generated_at=report.baseline_generated_at,
                    current_generated_at=report.current_generated_at,
                    trend=report.trend.value,
                    confidence=report.confidence,
                    methodology_version=report.methodology_version,
                    report_json=report.to_dict(),
                    report_path=report_path,
                )
                session.add(record)
            else:
                record.trend = report.trend.value
                record.confidence = report.confidence
                record.report_json = report.to_dict()
                record.report_path = report_path
            await session.commit()
            await session.refresh(record)
            return record.id
