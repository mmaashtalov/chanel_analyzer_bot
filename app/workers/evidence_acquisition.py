from __future__ import annotations

import asyncio
import contextlib
import logging

logger = logging.getLogger(__name__)


class EvidenceAcquisitionWorker:
    def __init__(self, service, repository, poll_seconds: int = 60) -> None:
        self._service = service
        self._repository = repository
        self._poll_seconds = max(30, poll_seconds)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="evidence-acquisition-worker")

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                for request in await self._repository.list_due(limit=10):
                    try:
                        await self._service.run(request["id"])
                    except Exception as exc:  # noqa: BLE001 - one request must not stop the durable queue
                        logger.warning("evidence_acquisition_failed request_id=%s error=%s", request["id"], exc)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("evidence_acquisition_loop_failed")
            await asyncio.sleep(self._poll_seconds)
