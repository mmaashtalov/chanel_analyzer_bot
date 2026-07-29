from __future__ import annotations

from app.application.review_claims import ReviewClaimsUseCase
from app.db.evidence_request_repository import EvidenceRequestRepository
from app.db.workspace_repository import WorkspaceRepository
from app.evidence.acquisition import (
    EvidenceRequestStatus,
    build_contradiction_request_plan,
    build_request_plan,
)


class ExternalRunner:
    async def run_owned(self, user_id: int, request_id: str) -> dict: ...


class AcquireEvidenceUseCase:
    def __init__(self, workspace_repository: WorkspaceRepository, review_use_case: ReviewClaimsUseCase,
                 request_repository: EvidenceRequestRepository, external_runner: ExternalRunner | None = None) -> None:
        self._workspaces = workspace_repository
        self._review = review_use_case
        self._requests = request_repository
        self._external_runner = external_runner

    async def create_for_claim(self, user_id: int, workspace_id: str, claim_id: str) -> dict:
        workspace = await self._workspaces.get(user_id, workspace_id)
        if workspace is None: raise LookupError("Workspace не найден")
        _bundle, claims = await self._review.list_claims(user_id, workspace_id)
        claim = next((item for item in claims if item["claim_id"] == claim_id), None)
        if claim is None: raise LookupError("Claim не найден в последнем bundle Workspace")
        _, gaps = await self._review.gaps(user_id, workspace_id)
        plan = build_request_plan(workspace, claim, gaps)
        return await self._requests.create(workspace_id, user_id, plan)

    async def create_for_contradiction(
        self,
        user_id: int,
        workspace_id: str,
        contradiction: dict,
    ) -> dict:
        workspace = await self._workspaces.get(user_id, workspace_id)
        if workspace is None:
            raise LookupError("Workspace не найден")
        plan = build_contradiction_request_plan(workspace, contradiction)
        return await self._requests.create(workspace_id, user_id, plan)

    async def list(self, user_id: int, workspace_id: str | None = None) -> list[dict]:
        if workspace_id is not None and await self._workspaces.get(user_id, workspace_id) is None:
            raise LookupError("Workspace не найден")
        return await self._requests.list_owned(user_id, workspace_id)

    async def cancel(self, user_id: int, request_id: str) -> dict:
        row = await self._requests.get_owned(request_id, user_id)
        if row is None: raise LookupError("Evidence request не найден")
        if row["status"] in {"resolved", "failed", "cancelled"}:
            raise ValueError("Завершённый request нельзя отменить")
        return await self._requests.transition(request_id, EvidenceRequestStatus.CANCELLED, details={"by": user_id})

    async def retry(self, user_id: int, request_id: str) -> dict:
        row = await self._requests.get_owned(request_id, user_id)
        if row is None: raise LookupError("Evidence request не найден")
        if row["attempts"] >= row["max_attempts"]:
            raise ValueError("Достигнут лимит повторов")
        if row["status"] not in {"failed", "partial"}:
            raise ValueError("Повтор разрешён только для failed или partial")
        return await self._requests.transition(request_id, EvidenceRequestStatus.QUEUED, details={"retry_by": user_id})

    async def run(self, user_id: int, request_id: str) -> dict:
        row = await self._requests.get_owned(request_id, user_id)
        if row is None:
            raise LookupError("Evidence request не найден")
        if row["status"] not in {"queued", "retry_wait", "partial", "failed"}:
            raise ValueError("Request сейчас нельзя запустить")
        if self._external_runner is not None:
            return await self._external_runner.run_owned(user_id, request_id)
        return await self._requests.fulfill_from_store(request_id)

    async def history(self, user_id: int, request_id: str) -> list[dict]:
        return await self._requests.history(request_id, user_id)
