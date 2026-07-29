from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.collection.base import ChannelDataProvider
from app.db.repositories import JobRepository, ProfileRepository
from app.domain.models import ChannelRef, ChannelSnapshot, JobStatus
from app.profiling import ContentDNAProfile, build_content_dna
from app.profiles import build_intelligence_profile
from app.reports.comparison_pdf import build_comparison_pdf
from app.similarity import SimilarityResult, compare_channels

ProgressCallback = Callable[[int, str], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class CompareChannelsResult:
    job_id: str
    snapshot_a: ChannelSnapshot
    snapshot_b: ChannelSnapshot
    profile_a: ContentDNAProfile
    profile_b: ContentDNAProfile
    similarity: SimilarityResult
    report_path: Path


class CompareChannelsUseCase:
    def __init__(self, provider: ChannelDataProvider, repository: JobRepository, report_output_dir: Path, lookback_days: int, profile_repository: ProfileRepository | None = None) -> None:
        self._provider = provider
        self._repository = repository
        self._report_output_dir = report_output_dir
        self._lookback_days = lookback_days
        self._profile_repository = profile_repository

    async def execute(self, telegram_user_id: int, channel_a: ChannelRef, channel_b: ChannelRef, progress: ProgressCallback | None = None) -> CompareChannelsResult:
        if channel_a.username == channel_b.username:
            raise ValueError("Для сравнения укажите два разных канала")
        job_id = await self._repository.create(telegram_user_id, f"{channel_a.username}|{channel_b.username}")

        async def report(step: int, text: str, status: JobStatus) -> None:
            await self._repository.update_progress(job_id, status, step, text)
            if progress:
                await progress(step, text)

        try:
            date_to = datetime.now(UTC)
            date_from = date_to - timedelta(days=self._lookback_days)
            await report(1, "Получаю публикации первого канала", JobStatus.COLLECTING)
            snapshot_a = await self._provider.fetch_channel(channel_a, date_from=date_from, date_to=date_to)
            await report(2, "Получаю публикации второго канала", JobStatus.COLLECTING)
            snapshot_b = await self._provider.fetch_channel(channel_b, date_from=date_from, date_to=date_to)
            if not snapshot_a.posts or not snapshot_b.posts:
                raise ValueError("Для одного из каналов не найдено текстовых публикаций")
            await report(3, "Строю Content DNA обоих каналов", JobStatus.ANALYZING)
            profile_a = build_content_dna(snapshot_a)
            profile_b = build_content_dna(snapshot_b)
            await report(4, "Сравниваю четыре пространства признаков", JobStatus.REPORTING)
            similarity = compare_channels(snapshot_a, profile_a, snapshot_b, profile_b)
            if self._profile_repository is not None:
                empty_metrics: dict[str, object] = {"source": "compare", "post_count": len(snapshot_a.posts)}
                await self._profile_repository.save_version(build_intelligence_profile(snapshot_a, profile_a, empty_metrics))
                empty_metrics_b: dict[str, object] = {"source": "compare", "post_count": len(snapshot_b.posts)}
                await self._profile_repository.save_version(build_intelligence_profile(snapshot_b, profile_b, empty_metrics_b))
            report_path = build_comparison_pdf(snapshot_a, snapshot_b, similarity, self._report_output_dir, job_id)
            await self._repository.save_comparison_result(job_id, similarity.to_dict(), str(report_path))
            if progress:
                await progress(5, "Сравнительный отчёт готов")
            return CompareChannelsResult(job_id, snapshot_a, snapshot_b, profile_a, profile_b, similarity, report_path)
        except Exception as exc:
            await self._repository.fail(job_id, str(exc))
            raise
