from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.analytics.metrics import QuantitativeMetrics, calculate_metrics
from app.collection.base import ChannelDataProvider
from app.db.repositories import EvolutionRepository, GraphRepository, JobRepository, ProfileRepository
from app.domain.models import ChannelRef, ChannelSnapshot, JobStatus
from app.graph import GraphSnapshot, build_graph_snapshot
from app.evolution import EvolutionReport, compare_profile_versions
from app.profiling import ContentDNAProfile, build_content_dna
from app.profiles import IntelligenceProfile, build_intelligence_profile
from app.reports.pdf import build_quantitative_pdf

ProgressCallback = Callable[[int, str], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class AnalyzeChannelResult:
    job_id: str
    snapshot: ChannelSnapshot
    metrics: QuantitativeMetrics
    report_path: Path
    content_dna: ContentDNAProfile
    intelligence_profile: IntelligenceProfile
    profile_version: int
    graph_snapshot: GraphSnapshot | None
    evolution_report: EvolutionReport | None


class AnalyzeChannelUseCase:
    def __init__(
        self,
        provider: ChannelDataProvider,
        repository: JobRepository,
        report_output_dir: Path,
        lookback_days: int,
        profile_repository: ProfileRepository | None = None,
        graph_repository: GraphRepository | None = None,
        evolution_repository: EvolutionRepository | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._report_output_dir = report_output_dir
        self._lookback_days = lookback_days
        self._profile_repository = profile_repository
        self._graph_repository = graph_repository
        self._evolution_repository = evolution_repository

    async def execute(
        self,
        telegram_user_id: int,
        channel: ChannelRef,
        progress: ProgressCallback | None = None,
    ) -> AnalyzeChannelResult:
        job_id = await self._repository.create(telegram_user_id, channel.username)

        async def report(step: int, text: str, status: JobStatus) -> None:
            await self._repository.update_progress(job_id, status, step, text)
            if progress:
                await progress(step, text)

        try:
            await report(1, "Получаю публикации", JobStatus.COLLECTING)
            date_to = datetime.now(UTC)
            date_from = date_to - timedelta(days=self._lookback_days)
            snapshot = await self._provider.fetch_channel(channel, date_from=date_from, date_to=date_to)
            if not snapshot.posts:
                raise ValueError("За выбранный период не найдено текстовых публикаций")

            await report(2, "Нормализую и проверяю данные", JobStatus.ANALYZING)
            await report(3, "Рассчитываю метрики", JobStatus.ANALYZING)
            metrics = calculate_metrics(snapshot)

            await report(4, "Строю Content DNA и PDF", JobStatus.REPORTING)
            content_dna = build_content_dna(snapshot)
            report_path = build_quantitative_pdf(
                snapshot, metrics, self._report_output_dir, job_id, content_dna=content_dna
            )
            result_payload = metrics.to_dict()
            result_payload["content_dna"] = content_dna.to_dict()
            intelligence_profile = build_intelligence_profile(snapshot, content_dna, result_payload)
            profile_version = 0
            profile_id = None
            graph_snapshot = None
            evolution_report = None
            previous_stored = None
            if self._profile_repository is not None:
                previous_stored = await self._profile_repository.get_latest(intelligence_profile.username)
                profile_id, profile_version = await self._profile_repository.save_version(intelligence_profile)
                if previous_stored is not None and profile_version > previous_stored.version:
                    evolution_report = compare_profile_versions(
                        previous_stored.profile, intelligence_profile, previous_stored.version, profile_version
                    )
                    if self._evolution_repository is not None:
                        await self._evolution_repository.save_report(profile_id, evolution_report)
            if self._graph_repository is not None and profile_id is not None:
                graph_snapshot = build_graph_snapshot(snapshot, profile_version)
                await self._graph_repository.save_snapshot(graph_snapshot, profile_id)
            if evolution_report is not None:
                result_payload["evolution"] = evolution_report.to_dict()
            result_payload["intelligence_profile"] = {
                "methodology_version": intelligence_profile.methodology_version,
                "confidence": intelligence_profile.confidence,
                "vector_dimension": len(intelligence_profile.combined_vector),
                "profile_version": profile_version,
            }
            await self._repository.save_result(
                job_id, snapshot, result_payload, str(report_path)
            )
            if progress:
                await progress(5, "Отчёт готов")
            return AnalyzeChannelResult(job_id, snapshot, metrics, report_path, content_dna, intelligence_profile, profile_version, graph_snapshot, evolution_report)
        except Exception as exc:
            await self._repository.fail(job_id, str(exc))
            raise
