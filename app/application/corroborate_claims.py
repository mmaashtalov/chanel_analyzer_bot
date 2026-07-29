from __future__ import annotations

from app.db.claim_review_repository import ClaimReviewRepository
from app.db.corroboration_repository import CorroborationRepository
from app.db.workspace_repository import WorkspaceRepository


class CorroborateClaimsUseCase:
    def __init__(
        self,
        workspaces: WorkspaceRepository,
        reviews: ClaimReviewRepository,
        corroboration: CorroborationRepository,
    ) -> None:
        self._workspaces = workspaces
        self._reviews = reviews
        self._corroboration = corroboration

    async def assess(self, telegram_user_id: int, workspace_id: str) -> dict:
        workspace = await self._workspaces.get(telegram_user_id, workspace_id)
        if workspace is None:
            raise LookupError("Workspace не найден")
        bundle = await self._reviews.latest_bundle_for_workspace(workspace_id)
        if bundle is None:
            raise LookupError("Для Workspace ещё нет provenance bundle")
        return await self._corroboration.assess_bundle(str(bundle["bundle_id"]))
