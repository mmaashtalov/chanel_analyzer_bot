from __future__ import annotations

from app.db.claim_review_repository import ClaimReviewRepository
from app.db.workspace_repository import WorkspaceRepository
from app.evidence.review import ClaimReviewStatus, detect_evidence_gaps


class ReviewClaimsUseCase:
    def __init__(
        self,
        workspace_repository: WorkspaceRepository,
        review_repository: ClaimReviewRepository,
    ) -> None:
        self._workspace_repository = workspace_repository
        self._review_repository = review_repository

    async def list_claims(
        self,
        telegram_user_id: int,
        workspace_id: str,
        status: ClaimReviewStatus | None = None,
    ) -> tuple[dict, list[dict]]:
        workspace = await self._workspace_repository.get(telegram_user_id, workspace_id)
        if workspace is None:
            raise LookupError("Workspace не найден")
        bundle = await self._review_repository.latest_bundle_for_workspace(workspace.id)
        if bundle is None:
            raise LookupError("Для Workspace ещё нет provenance bundle")
        claims = list(bundle.get("claims", []))
        if status is not None:
            claims = [
                item for item in claims
                if item.get("review_status", "unreviewed") == status.value
            ]
        return bundle, claims

    async def review(
        self,
        telegram_user_id: int,
        claim_id: str,
        status: ClaimReviewStatus,
        comment: str | None,
    ) -> dict:
        context = await self._review_repository.claim_context(claim_id)
        if context is None:
            raise LookupError("Claim не найден")
        if not await self._owned_workspace(telegram_user_id, context):
            raise PermissionError("Claim не принадлежит Workspace пользователя")
        return await self._review_repository.review_claim(
            claim_id, telegram_user_id, status, comment
        )

    async def gaps(self, telegram_user_id: int, workspace_id: str):
        bundle, _ = await self.list_claims(telegram_user_id, workspace_id)
        return bundle, detect_evidence_gaps(bundle)

    async def history(self, telegram_user_id: int, claim_id: str) -> list[dict]:
        context = await self._review_repository.claim_context(claim_id)
        if context is None:
            raise LookupError("Claim не найден")
        if not await self._owned_workspace(telegram_user_id, context):
            raise PermissionError("Claim не принадлежит Workspace пользователя")
        return await self._review_repository.history(claim_id)

    async def _owned_workspace(self, telegram_user_id: int, context: dict) -> bool:
        workspace_ids = [str(item) for item in context.get("workspace_ids", [])]
        if not workspace_ids and context.get("subject_type") != "channel_analysis":
            workspace_ids = [str(context["subject_id"]).split(":", 1)[0]]
        return any(
            await self._workspace_repository.get(telegram_user_id, workspace_id) is not None
            for workspace_id in workspace_ids
        )
