from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from app.db.evidence_request_repository import EvidenceRequestRepository
from app.db.source_collection_repository import CollectionStats, SourceCollectionRepository
from app.evidence.acquisition import EvidenceRequestStatus
from app.sources import SourceRegistry, SourceRequest


@dataclass(slots=True, frozen=True)
class ExternalAcquisitionLimits:
    lookback_days: int = 30
    max_sources: int = 10
    max_documents_per_source: int = 50
    timeout_seconds: int = 30
    backoff_seconds: int = 60


class ControlledExternalAcquisition:
    def __init__(
        self, registry: SourceRegistry, request_repository: EvidenceRequestRepository,
        collection_repository: SourceCollectionRepository, limits: ExternalAcquisitionLimits,
    ) -> None:
        self._registry = registry
        self._requests = request_repository
        self._collections = collection_repository
        self._limits = limits

    async def run_owned(self, user_id: int, request_id: str) -> dict:
        row = await self._requests.get_owned(request_id, user_id)
        if row is None:
            raise LookupError("Evidence request не найден")
        return await self.run(request_id)

    async def run(self, request_id: str) -> dict:
        row = await self._requests.get(request_id)
        if row is None:
            raise LookupError("Evidence request не найден")
        if row["status"] not in {"queued", "retry_wait", "partial", "failed"}:
            raise ValueError("Request сейчас нельзя запустить")
        if row["attempts"] >= row["max_attempts"]:
            raise ValueError("Достигнут лимит повторов")

        if await self._requests.count_local_candidates(request_id) > 0:
            return await self._requests.link_from_store(request_id, increment_attempt=True, stage="local_first")

        row = await self._requests.begin_collection(request_id)
        now = datetime.now(UTC)
        date_from = now - timedelta(days=self._limits.lookback_days)
        summaries: list[CollectionStats] = []
        errors: list[dict[str, str]] = []
        plan = row["source_plan"][: self._limits.max_sources]

        for item in plan:
            source_type = str(item.get("source_type", ""))
            source_id = str(item.get("source_id", ""))
            try:
                adapter = self._registry.get(source_type)
                documents = await asyncio.wait_for(
                    adapter.collect(SourceRequest(
                        source_id=source_id, date_from=date_from, date_to=now,
                        limit=self._limits.max_documents_per_source,
                    )),
                    timeout=self._limits.timeout_seconds,
                )
                summaries.append(await self._collections.persist(adapter, source_id, documents))
            except Exception as exc:
                errors.append({"source_type": source_type, "source_id": source_id, "error": str(exc)[:500]})
                try:
                    adapter = self._registry.get(source_type)
                    await self._collections.record_failure(adapter, source_id, exc)
                except Exception:
                    pass

        collected = sum(item.collected for item in summaries)
        accepted = sum(item.accepted for item in summaries)
        await self._requests.record_collection(
            request_id, collected=collected, summary={
                "sources": [asdict(item) for item in summaries],
                "errors": errors,
                "accepted": accepted,
            },
        )
        result = await self._requests.link_from_store(
            request_id, increment_attempt=False, stage="external_collection"
        )
        if result["status"] == EvidenceRequestStatus.FAILED.value and errors and result["attempts"] < result["max_attempts"]:
            delay = self._limits.backoff_seconds * (2 ** max(result["attempts"] - 1, 0))
            return await self._requests.schedule_retry(
                request_id, delay_seconds=delay, error=f"Ошибки источников: {len(errors)}"
            )
        return result
