from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.analytics.metrics import QuantitativeMetrics, calculate_metrics
from app.collection.base import ChannelDataProvider
from app.db.evidence_repository import EvidenceRepository
from app.db.repositories import (
    EvolutionRepository,
    GraphRepository,
    JobRepository,
    ProfileRepository,
)
from app.db.source_collection_repository import CollectionStats, SourceCollectionRepository
from app.db.workspace_repository import WorkspaceRepository
from app.domain.models import ChannelRef, ChannelSnapshot, JobStatus
from app.evidence.engine import build_channel_analysis_provenance
from app.evidence.models import ProvenanceBundle
from app.evolution import EvolutionReport, compare_profile_versions
from app.graph import GraphSnapshot, build_graph_snapshot
from app.profiles import IntelligenceProfile, build_intelligence_profile
from app.profiling import ContentDNAProfile, build_content_dna
from app.reports.pdf import build_provenance_json, build_quantitative_pdf
from app.sources.adapters.telegram import documents_from_snapshot
from app.sources.base import SourceAdapter

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
    provenance: ProvenanceBundle
    provenance_path: Path


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
        source_adapter: SourceAdapter | None = None,
        source_collection_repository: SourceCollectionRepository | None = None,
        evidence_repository: EvidenceRepository | None = None,
        workspace_repository: WorkspaceRepository | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._report_output_dir = report_output_dir
        self._lookback_days = lookback_days
        self._profile_repository = profile_repository
        self._graph_repository = graph_repository
        self._evolution_repository = evolution_repository
        self._source_adapter = source_adapter
        self._source_collection_repository = source_collection_repository
        self._evidence_repository = evidence_repository
        self._workspace_repository = workspace_repository

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
            documents = documents_from_snapshot(snapshot)
            if not documents:
                raise ValueError("За выбранный период не найдено текстовых публикаций")
            workspaces = (
                await self._workspace_repository.list_for_channel(telegram_user_id, channel.username)
                if self._workspace_repository is not None
                else []
            )
            workspace_ids = tuple(workspace.id for workspace in workspaces)
            if workspace_ids and self._evidence_repository is None:
                raise RuntimeError("Для связи provenance с Workspace нужен EvidenceRepository")

            await report(2, "Нормализую и проверяю данные", JobStatus.ANALYZING)
            collection_stats: CollectionStats | None = None
            document_record_ids: dict[str, str] = {}
            if self._source_adapter is not None and self._source_collection_repository is not None:
                collection_stats = await self._source_collection_repository.persist(
                    self._source_adapter,
                    channel.username,
                    documents,
                )
                if len(collection_stats.document_ids) != len(documents):
                    raise RuntimeError("Source Registry вернул неполную карту сохранённых документов")
                document_record_ids = {
                    document.document_id: record_id
                    for document, record_id in zip(documents, collection_stats.document_ids, strict=True)
                }
            await report(3, "Рассчитываю метрики", JobStatus.ANALYZING)
            metrics = calculate_metrics(snapshot)

            await report(4, "Строю Content DNA, provenance и PDF", JobStatus.REPORTING)
            content_dna = build_content_dna(snapshot)
            provenance = build_channel_analysis_provenance(
                snapshot,
                documents,
                metrics,
                content_dna,
                job_id=job_id,
                document_record_ids=document_record_ids,
                collection_stats=asdict(collection_stats) if collection_stats is not None else None,
                workspace_ids=workspace_ids,
            )
            report_path = build_quantitative_pdf(
                snapshot,
                metrics,
                self._report_output_dir,
                job_id,
                content_dna=content_dna,
                provenance=provenance,
            )
            provenance_path = build_provenance_json(
                provenance,
                self._report_output_dir,
                channel.username,
                job_id,
            )
            if self._evidence_repository is not None:
                await self._evidence_repository.save(provenance)
                for workspace_id in workspace_ids:
                    await self._evidence_repository.link_to_workspace(
                        provenance.bundle_id,
                        workspace_id,
                        channel.username,
                    )
            result_payload = metrics.to_dict()
            result_payload["content_dna"] = content_dna.to_dict()
            result_payload["provenance"] = {
                "bundle_id": provenance.bundle_id,
                "subject_id": provenance.subject_id,
                "methodology_version": provenance.methodology_version,
                "integrity_hash": provenance.integrity_hash,
                "completeness": provenance.completeness,
                "claims": len(provenance.claims),
                "evidence_references": len(provenance.evidence),
                "json_path": str(provenance_path),
                "workspace_ids": list(workspace_ids),
            }
            if collection_stats is not None:
                result_payload["source_collection"] = {
                    "source_type": collection_stats.source_type,
                    "source_id": collection_stats.source_id,
                    "collected": collection_stats.collected,
                    "accepted": collection_stats.accepted,
                    "duplicates": collection_stats.duplicates,
                }
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
            return AnalyzeChannelResult(
                job_id=job_id,
                snapshot=snapshot,
                metrics=metrics,
                report_path=report_path,
                content_dna=content_dna,
                intelligence_profile=intelligence_profile,
                profile_version=profile_version,
                graph_snapshot=graph_snapshot,
                evolution_report=evolution_report,
                provenance=provenance,
                provenance_path=provenance_path,
            )
        except Exception as exc:
            await self._repository.fail(job_id, str(exc))
            raise
