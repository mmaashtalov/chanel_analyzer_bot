from __future__ import annotations

import asyncio
import contextlib

import structlog

logger = structlog.get_logger()


class MonitoringWorker:
    def __init__(self, service, repository, bot, poll_seconds: int = 60) -> None:
        self._service = service
        self._repository = repository
        self._bot = bot
        self._poll_seconds = max(30, poll_seconds)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="monitoring-worker")

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
                results = await self._service.check_due()
                for watch, alerts, error in results:
                    if error is not None:
                        logger.warning("watch_check_failed", channel=watch.channel_username, error=str(error))
                        continue
                    for alert in alerts:
                        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}[alert.severity.value]
                        text = (
                            f"{icon} {alert.severity.value.upper()} · @{watch.channel_username}\n\n"
                            f"{alert.title}\n{alert.description}\n\nConfidence: {alert.confidence:.0%}"
                        )
                        try:
                            message = await self._bot.send_message(chat_id=watch.chat_id, text=text)
                            await self._repository.mark_delivered(alert.fingerprint, watch.id, watch.chat_id, message.message_id)
                        except Exception as exc:
                            await self._repository.mark_delivery_failed(alert.fingerprint, watch.id, watch.chat_id, str(exc))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("monitoring_loop_failed")
            await asyncio.sleep(self._poll_seconds)
