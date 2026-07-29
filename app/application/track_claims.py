from __future__ import annotations

from app.db.temporal_claim_repository import TemporalClaimRepository
from app.db.workspace_repository import WorkspaceRepository


class TrackClaimsUseCase:
    def __init__(self, workspaces: WorkspaceRepository, temporal: TemporalClaimRepository) -> None:
        self._workspaces = workspaces
        self._temporal = temporal

    async def build(self, telegram_user_id: int, workspace_id: str) -> dict:
        if await self._workspaces.get(telegram_user_id, workspace_id) is None:
            raise LookupError("Workspace не найден")
        return await self._temporal.build_workspace_timeline(workspace_id)

    async def timeline(self, telegram_user_id: int, claim_id: str) -> dict:
        report = await self._temporal.claim_timeline(claim_id)
        workspace_id = report.get("workspace_id")
        if not workspace_id or await self._workspaces.get(telegram_user_id, workspace_id) is None:
            raise LookupError("Claim не найден")
        return report
