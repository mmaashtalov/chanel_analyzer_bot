from __future__ import annotations

from datetime import UTC, datetime

from app.domain.models import ChannelRef
from app.monitoring.engine import alerts_from_evolution


class MonitoringService:
    def __init__(self, analyze_use_case, monitoring_repository) -> None:
        self._analyze = analyze_use_case
        self._repository = monitoring_repository

    async def check_watch(self, watch):
        try:
            result = await self._analyze.execute(watch.telegram_user_id, ChannelRef(watch.channel_username))
            alerts = ()
            if result.evolution_report is not None:
                candidates = alerts_from_evolution(result.evolution_report, watch.sensitivity)
                alerts = await self._repository.save_alerts(watch, result.profile_version or 0, candidates)
            await self._repository.mark_checked(watch.id, result.profile_version, None)
            return alerts
        except Exception as exc:
            await self._repository.mark_checked(watch.id, watch.last_profile_version, str(exc))
            raise

    async def check_due(self, limit: int = 25):
        watches = await self._repository.due(datetime.now(UTC), limit)
        results = []
        for watch in watches:
            try:
                alerts = await self.check_watch(watch)
                results.append((watch, alerts, None))
            except Exception as exc:
                results.append((watch, (), exc))
        return results
