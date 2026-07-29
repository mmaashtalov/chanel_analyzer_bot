from pathlib import Path

from app.db.workspace_intelligence_repository import WorkspaceIntelligenceRepository
from app.db.workspace_repository import WorkspaceRepository
from app.reports.workspace_pdf import build_workspace_pdf
from app.workspace_intelligence.engine import build_workspace_intelligence


class WorkspaceReportUseCase:
    def __init__(
        self,
        workspace_repository: WorkspaceRepository,
        intelligence_repository: WorkspaceIntelligenceRepository,
        output_dir: Path,
    ) -> None:
        self._workspace_repository = workspace_repository
        self._intelligence_repository = intelligence_repository
        self._output_dir = output_dir

    async def execute(self, telegram_user_id: int, workspace_id: str, lookback_days: int = 30):
        workspace = await self._workspace_repository.get(telegram_user_id, workspace_id)
        if workspace is None:
            raise LookupError("Workspace не найден")
        data = await self._intelligence_repository.build_input(workspace, lookback_days)
        report = build_workspace_intelligence(data)
        path = build_workspace_pdf(report, self._output_dir)
        await self._intelligence_repository.save_snapshot(report, str(path))
        return report, path
