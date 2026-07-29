import asyncio

import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler

from app.application.acquire_evidence import AcquireEvidenceUseCase
from app.application.analyze_channel import AnalyzeChannelUseCase
from app.application.compare_channels import CompareChannelsUseCase
from app.application.corroborate_claims import CorroborateClaimsUseCase
from app.application.external_acquisition import (
    ControlledExternalAcquisition,
    ExternalAcquisitionLimits,
)
from app.application.find_similar_profiles import FindSimilarProfilesUseCase
from app.application.review_claims import ReviewClaimsUseCase
from app.application.track_claims import TrackClaimsUseCase
from app.application.triage_contradictions import TriageContradictionsUseCase
from app.application.workspace_changes import WorkspaceChangesUseCase
from app.application.workspace_report import WorkspaceReportUseCase
from app.bot.handlers import build_handlers
from app.collection.factory import build_provider
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.claim_review_repository import ClaimReviewRepository
from app.db.contradiction_repository import ContradictionRepository
from app.db.corroboration_repository import CorroborationRepository
from app.db.document_evidence_repository import DocumentEvidenceRepository
from app.db.evidence_repository import EvidenceRepository
from app.db.evidence_request_repository import EvidenceRequestRepository
from app.db.repositories import (
    EvolutionRepository,
    GraphRepository,
    JobRepository,
    MonitoringRepository,
    ProfileRepository,
)
from app.db.session import build_engine, build_session_factory, create_schema
from app.db.source_collection_repository import SourceCollectionRepository
from app.db.temporal_claim_repository import TemporalClaimRepository
from app.db.workspace_evolution_repository import WorkspaceEvolutionRepository
from app.db.workspace_intelligence_repository import WorkspaceIntelligenceRepository
from app.db.workspace_repository import WorkspaceRepository
from app.monitoring.service import MonitoringService
from app.sources import SourceRegistry
from app.sources.adapters import RSSSourceAdapter, TelegramSourceAdapter
from app.sources.http import safe_fetch
from app.workers.evidence_acquisition import EvidenceAcquisitionWorker
from app.workers.monitoring import MonitoringWorker


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger()

    engine = build_engine(settings.database_url)
    await create_schema(engine)
    session_factory = build_session_factory(engine)
    repository = JobRepository(session_factory)
    profile_repository = ProfileRepository(session_factory)
    graph_repository = GraphRepository(session_factory)
    evolution_repository = EvolutionRepository(session_factory)
    monitoring_repository = MonitoringRepository(session_factory)
    workspace_repository = WorkspaceRepository(session_factory)
    workspace_intelligence_repository = WorkspaceIntelligenceRepository(session_factory)
    workspace_evolution_repository = WorkspaceEvolutionRepository(session_factory)
    evidence_repository = EvidenceRepository(session_factory)
    document_evidence_repository = DocumentEvidenceRepository(session_factory)
    claim_review_repository = ClaimReviewRepository(session_factory)
    evidence_request_repository = EvidenceRequestRepository(session_factory)
    source_collection_repository = SourceCollectionRepository(session_factory)
    corroboration_repository = CorroborationRepository(session_factory)
    temporal_claim_repository = TemporalClaimRepository(session_factory)
    contradiction_repository = ContradictionRepository(session_factory)
    provider = build_provider(settings)
    source_registry = SourceRegistry()
    telegram_source_adapter = TelegramSourceAdapter(provider)
    source_registry.register(telegram_source_adapter)
    source_registry.register(RSSSourceAdapter(
        lambda url: safe_fetch(
            url,
            timeout=settings.evidence_acquisition_timeout_seconds,
            max_bytes=settings.evidence_acquisition_max_feed_bytes,
        )
    ))
    external_acquisition = ControlledExternalAcquisition(
        source_registry,
        evidence_request_repository,
        source_collection_repository,
        ExternalAcquisitionLimits(
            lookback_days=settings.evidence_acquisition_lookback_days,
            max_sources=settings.evidence_acquisition_max_sources,
            max_documents_per_source=settings.evidence_acquisition_max_documents_per_source,
            timeout_seconds=settings.evidence_acquisition_timeout_seconds,
            backoff_seconds=settings.evidence_acquisition_backoff_seconds,
        ),
    )
    use_case = AnalyzeChannelUseCase(
        provider=provider,
        repository=repository,
        report_output_dir=settings.report_output_dir,
        lookback_days=settings.analysis_lookback_days,
        profile_repository=profile_repository,
        graph_repository=graph_repository,
        evolution_repository=evolution_repository,
        source_adapter=telegram_source_adapter,
        source_collection_repository=source_collection_repository,
        evidence_repository=evidence_repository,
        workspace_repository=workspace_repository,
    )
    compare_use_case = CompareChannelsUseCase(provider, repository, settings.report_output_dir, settings.analysis_lookback_days, profile_repository)
    similar_use_case = FindSimilarProfilesUseCase(profile_repository)
    workspace_report_use_case = WorkspaceReportUseCase(
        workspace_repository, workspace_intelligence_repository, settings.report_output_dir
    )
    review_claims_use_case = ReviewClaimsUseCase(workspace_repository, claim_review_repository)
    acquire_evidence_use_case = AcquireEvidenceUseCase(
        workspace_repository, review_claims_use_case, evidence_request_repository, external_acquisition
    )
    corroborate_claims_use_case = CorroborateClaimsUseCase(
        workspace_repository, claim_review_repository, corroboration_repository
    )
    track_claims_use_case = TrackClaimsUseCase(workspace_repository, temporal_claim_repository)
    contradiction_use_case = TriageContradictionsUseCase(
        workspace_repository,
        contradiction_repository,
        acquire_evidence_use_case,
    )
    workspace_changes_use_case = WorkspaceChangesUseCase(
        workspace_repository, workspace_evolution_repository, settings.report_output_dir, evidence_repository,
        document_evidence_repository
    )
    (
        start_handler, analyze_handler, compare_handler, similar_handler, network_handler,
        entity_handler, domain_handler, timeline_handler, changes_handler, history_handler,
        watch_handler, unwatch_handler, watches_handler, alerts_handler, digest_handler,
        workspace_create_handler, workspaces_handler, workspace_show_handler, workspace_add_handler,
        workspace_remove_handler, workspace_delete_handler, workspace_report_handler, workspace_changes_handler,
        claims_handler, claim_review_handler, claim_history_handler, evidence_gaps_handler, verification_report_handler, corroboration_handler, claim_timeline_build_handler, claim_timeline_handler, claim_timeline_report_handler, evidence_request_handler, evidence_requests_handler, evidence_request_cancel_handler, evidence_request_retry_handler, evidence_request_run_handler, evidence_request_history_handler, status_handler,
        contradictions_handler, contradiction_handler, contradiction_resolve_handler, contradiction_report_handler,
    ) = build_handlers(
        use_case, compare_use_case, similar_use_case, repository, graph_repository,
        evolution_repository, monitoring_repository, workspace_repository, workspace_report_use_case, workspace_changes_use_case, review_claims_use_case, acquire_evidence_use_case, corroborate_claims_use_case, track_claims_use_case, contradiction_use_case, settings.report_output_dir,
    )

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("analyze", analyze_handler))
    application.add_handler(CommandHandler("compare", compare_handler))
    application.add_handler(CommandHandler("similar", similar_handler))
    application.add_handler(CommandHandler("network", network_handler))
    application.add_handler(CommandHandler("entity", entity_handler))
    application.add_handler(CommandHandler("domain", domain_handler))
    application.add_handler(CommandHandler("timeline", timeline_handler))
    application.add_handler(CommandHandler("changes", changes_handler))
    application.add_handler(CommandHandler("history", history_handler))
    application.add_handler(CommandHandler("watch", watch_handler))
    application.add_handler(CommandHandler("unwatch", unwatch_handler))
    application.add_handler(CommandHandler("watches", watches_handler))
    application.add_handler(CommandHandler("alerts", alerts_handler))
    application.add_handler(CommandHandler("digest", digest_handler))
    application.add_handler(CommandHandler("workspace_create", workspace_create_handler))
    application.add_handler(CommandHandler("workspaces", workspaces_handler))
    application.add_handler(CommandHandler("workspace", workspace_show_handler))
    application.add_handler(CommandHandler("workspace_add", workspace_add_handler))
    application.add_handler(CommandHandler("workspace_remove", workspace_remove_handler))
    application.add_handler(CommandHandler("workspace_delete", workspace_delete_handler))
    application.add_handler(CommandHandler("workspace_report", workspace_report_handler))
    application.add_handler(CommandHandler("workspace_changes", workspace_changes_handler))
    application.add_handler(CommandHandler("claims", claims_handler))
    application.add_handler(CommandHandler("claim_review", claim_review_handler))
    application.add_handler(CommandHandler("claim_history", claim_history_handler))
    application.add_handler(CommandHandler("evidence_gaps", evidence_gaps_handler))
    application.add_handler(CommandHandler("verification_report", verification_report_handler))
    application.add_handler(CommandHandler("corroboration", corroboration_handler))
    application.add_handler(CommandHandler("claim_timeline_build", claim_timeline_build_handler))
    application.add_handler(CommandHandler("claim_timeline", claim_timeline_handler))
    application.add_handler(CommandHandler("claim_timeline_report", claim_timeline_report_handler))
    application.add_handler(CommandHandler("contradictions", contradictions_handler))
    application.add_handler(CommandHandler("contradiction", contradiction_handler))
    application.add_handler(CommandHandler("contradiction_resolve", contradiction_resolve_handler))
    application.add_handler(CommandHandler("contradiction_report", contradiction_report_handler))
    application.add_handler(CommandHandler("evidence_request", evidence_request_handler))
    application.add_handler(CommandHandler("evidence_requests", evidence_requests_handler))
    application.add_handler(CommandHandler("evidence_request_cancel", evidence_request_cancel_handler))
    application.add_handler(CommandHandler("evidence_request_retry", evidence_request_retry_handler))
    application.add_handler(CommandHandler("evidence_request_run", evidence_request_run_handler))
    application.add_handler(CommandHandler("evidence_request_history", evidence_request_history_handler))
    application.add_handler(CommandHandler("status", status_handler))

    monitoring_worker = MonitoringWorker(
        MonitoringService(use_case, monitoring_repository),
        monitoring_repository,
        application.bot,
        settings.monitoring_poll_seconds,
    )
    evidence_acquisition_worker = EvidenceAcquisitionWorker(
        external_acquisition, evidence_request_repository, settings.evidence_acquisition_poll_seconds
    )
    logger.info("application_starting", env=settings.app_env, provider=settings.data_provider)
    try:
        async with application:
            await application.start()
            if settings.monitoring_enabled:
                await monitoring_worker.start()
            if settings.evidence_acquisition_enabled:
                await evidence_acquisition_worker.start()
            if application.updater is None:
                raise RuntimeError("Telegram updater не создан")
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            await asyncio.Event().wait()
    finally:
        await evidence_acquisition_worker.stop()
        await monitoring_worker.stop()
        await source_registry.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
