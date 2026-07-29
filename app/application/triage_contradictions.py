from __future__ import annotations

from app.application.acquire_evidence import AcquireEvidenceUseCase
from app.db.contradiction_repository import ContradictionRepository
from app.db.workspace_repository import WorkspaceRepository
from app.evidence.contradictions import (
    ContradictionResolutionAction,
    ContradictionStatus,
)


class TriageContradictionsUseCase:
    def __init__(
        self,
        workspaces: WorkspaceRepository,
        contradictions: ContradictionRepository,
        acquire_evidence: AcquireEvidenceUseCase | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._contradictions = contradictions
        self._acquire_evidence = acquire_evidence

    async def queue(
        self,
        telegram_user_id: int,
        workspace_id: str,
        status_filter: str = "open",
        limit: int = 20,
    ) -> list[dict]:
        await self._require_workspace(telegram_user_id, workspace_id)
        return await self._contradictions.list_queue(workspace_id, status_filter, limit)

    async def detail(self, telegram_user_id: int, contradiction_id: str) -> dict:
        item = await self._owned(telegram_user_id, contradiction_id)
        if item is None:
            raise LookupError("Contradiction не найден")
        return item

    async def resolve(
        self,
        telegram_user_id: int,
        contradiction_id: str,
        action: ContradictionResolutionAction | str,
        selected_claim_id: str | None = None,
        comment: str | None = None,
    ) -> dict:
        item = await self._owned(telegram_user_id, contradiction_id)
        if item is None:
            raise LookupError("Contradiction не найден")
        parsed_action = (
            ContradictionResolutionAction.parse(action)
            if isinstance(action, str)
            else action
        )
        details: dict = {}
        if (
            parsed_action is ContradictionResolutionAction.REQUEST_EVIDENCE
            and self._acquire_evidence is not None
        ):
            request = await self._acquire_evidence.create_for_contradiction(
                telegram_user_id,
                item["workspace_id"],
                item,
            )
            details["evidence_request_id"] = request["id"]
        result = await self._contradictions.resolve(
            contradiction_id,
            telegram_user_id,
            parsed_action,
            selected_claim_id,
            comment,
            details,
        )
        if details:
            result["evidence_request_id"] = details.get("evidence_request_id")
        return result

    async def history(self, telegram_user_id: int, contradiction_id: str) -> list[dict]:
        item = await self._owned(telegram_user_id, contradiction_id)
        if item is None:
            raise LookupError("Contradiction не найден")
        return await self._contradictions.history(contradiction_id)

    async def report(
        self,
        telegram_user_id: int,
        workspace_id: str,
        status_filter: str = "all",
    ) -> dict:
        await self._require_workspace(telegram_user_id, workspace_id)
        return await self._contradictions.dossier(workspace_id, status_filter)

    async def _owned(self, telegram_user_id: int, contradiction_id: str) -> dict | None:
        context = await self._contradictions.context(contradiction_id)
        if context is None:
            return None
        if await self._workspaces.get(telegram_user_id, context["workspace_id"]) is None:
            raise PermissionError("Contradiction не принадлежит Workspace пользователя")
        return await self._contradictions.get(contradiction_id)

    async def _require_workspace(self, telegram_user_id: int, workspace_id: str) -> None:
        if await self._workspaces.get(telegram_user_id, workspace_id) is None:
            raise LookupError("Workspace не найден")


def parse_status_filter(raw: str | None) -> str:
    if not raw:
        return "open"
    if raw.casefold() in {"all", "open", "unresolved", "pending"}:
        return raw
    return ContradictionStatus.parse(raw).value
