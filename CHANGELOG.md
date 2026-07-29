# Changelog

## 0.22.0-product

- Добавлен Product Control Center.
- Добавлена безопасная форма ввода Telegram credentials.
- Добавлено хранение конфигурации в отдельном volume с chmod 0600.
- Добавлено управление migrate/start/stop/restart.
- Эмулятор встроен в тот же интерфейс.
- Docker Compose запускает PostgreSQL и Control Center одной командой.
- Добавлены product runbook и emulator guide.
- Regression-счётчик вычисляется из фактического дерева и фиксируется в `MANIFEST.json`.

# 0.21.2-demo — Demo Hardening

- Guided demonstration flow.
- Readiness and detailed self-test endpoints.
- SHA-256 validation of bundled demo artifacts.
- Fail-closed health status for missing/corrupt assets.

## 0.21.0 — Sprint 20

- Added stable claim identities across provenance bundles.
- Added deterministic temporal relations: supports, updates, supersedes, contradicts.
- Added temporal statuses: current, superseded, contradicted, resolved.
- Added immutable SHA-256 timeline relation events.
- Added Telegram claim timeline commands and PDF/JSON exports.
- Added migration 0016_temporal_claim_tracking.
- Full regression: 84 tests.

## 0.20.0 — Sprint 19

- Added deterministic Source Independence & Corroboration Engine.
- Added reprint/upstream clustering by hashes, domain and text similarity.
- Added independence and corroboration scores to analytic claims.
- Added pseudo-independent evidence gap and Telegram `/corroboration`.
- Added Alembic migration `0015_source_independence`.
- Expanded regression suite to 78 tests.

# 0.18.0 — Sprint 17

- Evidence acquisition request lifecycle.
- Source planning from Workspace.
- Local-first primary document linking.
- Retry/cancel/history controls.
- Migration 0013.
- 67 regression tests.

## 0.16.0 — Sprint 15
- Document-level provenance linked to stored Telegram, RSS and web documents.
- Deterministic document evidence IDs, excerpts, URLs, authors and fingerprints.
- Workspace-scoped evidence retrieval and claim-level relevance ranking.
- Primary-document appendix in Workspace Evolution PDF.
- Alembic migration 0011.

## 0.13.0 — Sprint 12
- Workspace Intelligence Engine with deterministic aggregation.
- Coverage, weighted metrics, entities, domains, keywords and alerts.
- Reproducible Workspace findings with confidence and evidence labels.
- Versioned workspace intelligence snapshots.
- `/workspace_report ID [days]` PDF command.
- Alembic migration 0008.

# Changelog

## 0.10.0 — Sprint 9

- Added persistent watchlists and configurable sensitivity thresholds.
- Added background monitoring worker and due-watch scheduling.
- Added alert generation from Evolution Reports.
- Added deterministic alert deduplication and delivery audit records.
- Added `/watch`, `/unwatch`, `/watches`, `/alerts`, and `/digest`.
- Added automatic suspension after repeated collection failures.
- Added Alembic migration `0005_monitoring_alerts`.
- Added monitoring tests.

# 0.9.0

- Evolution Engine for adjacent Intelligence Profile versions.
- Metric, Content DNA, narrative, temporal and structural change detection.
- Severity, confidence, evidence IDs and deterministic event fingerprints.
- `profile_changes` storage and Alembic migration 0004.
- Telegram commands `/changes` and `/history`.

# Changelog

## 0.8.0 — Sprint 7

- Intelligence Graph Engine.
- Deterministic entity extraction and evidence mapping.
- Versioned graph snapshots persisted in PostgreSQL.
- Entity, domain and monthly timeline queries.
- Telegram commands `/entity`, `/domain`, `/timeline`.
- Alembic migration `0003_intelligence_graph`.
- 20 automated tests passing.

# Changelog

## 0.7.0 — Sprint 6

- Added persistent profile search and `/similar`.
- Added component-aware re-ranking after pgvector HNSW candidate retrieval.
- Added false-positive controls for topic-only similarity.
- Added confidence, classification and explanations.
- Added `/network` one-hop PDF visualization.
- Added profile reconstruction repository methods and tests.


## 0.4.0 — Sprint 3
- Added deterministic Content DNA Engine with strict typed profile.
- Added reproducible stratified sampling across reach, length, date, weekday and hour.
- Added text normalization that preserves punctuation, case, emoji and paragraph structure.
- Added lexical, syntactic, punctuation, formatting and audience-address markers.
- Added trait scores with confidence, evidence posts and explicit methodology limitations.
- Added repeated phrase extraction and JSON persistence inside analysis results.
- Added four Content DNA pages to the PDF report.
- Added provider-neutral boundary for later LLM enrichment.
- Added automated tests for sampling, evidence and profile serialization.

## 0.3.0 — Sprint 2
- Advanced analytics: percentiles, stability, silence and burst detection.
- Correlations for length, reach, links and engagement.
- Statistical anomaly detection using robust MAD scores.
- Semantic core: terms and bigrams without LLM.
- Executive summary and new PDF sections.
- Added automated tests.

## 0.2.0 — Sprint 1
- Добавлен реальный Telethon MTProto provider.
- Добавлена PostgreSQL-схема заданий и постов.
- Добавлены `/analyze` и `/status`.
- Реализован пятиэтапный пайплайн анализа.
- Расширен набор количественных метрик.
- Добавлен многостраничный PDF-отчёт.
- Добавлены Alembic migration, Docker и тесты.

## 0.6.0 — Sprint 5

- Added persistent channel Intelligence Profiles.
- Added immutable profile version history.
- Added deterministic 256-dimensional feature vectors.
- Added pgvector cosine-nearest-neighbour repository.
- Added HNSW index migration for current profile versions.
- Switched Docker PostgreSQL image to pgvector/pgvector:pg17.
- Analysis and comparison flows now persist profile versions.

## 0.11.0 — Sprint 10: Multi-Source Core

- Added source adapter protocol and registry.
- Added `UnifiedDocument` with stable source and cross-source fingerprints.
- Added Telegram-to-document adapter.
- Added RSS/Atom adapter with injectable fetcher.
- Added exact deduplication and cross-source duplicate grouping.
- Added source health contracts.
- Added PostgreSQL models and Alembic migration for sources, runs, documents and errors.

## 0.12.0 — Sprint 11
- Intelligence Workspaces and typed workspace objects.
- Telegram commands for create/list/show/add/remove/delete.
- Ownership isolation, normalization and duplicate protection.
- Alembic migration 0007.

## 0.14.0 — Sprint 13

- Added Workspace Evolution Engine and deterministic trend classification.
- Added metric, entity, domain, keyword and alert deltas between snapshots.
- Added explicit Observation / Evidence / Confidence / Assessment records.
- Added `/workspace_changes <workspace_id> [days]` and evolution PDF.
- Added persistent `workspace_evolution_reports` with idempotent snapshot-pair storage.
- Added Alembic migration `0009_workspace_evolution`.
- 50 automated tests passing.

## 0.15.0 - Sprint 14

- Added Evidence & Provenance Engine with deterministic claim and evidence identifiers.
- Added claim-to-evidence graph, integrity hashes, evidence quality and completeness scoring.
- Persisted provenance bundles, analytic claims, evidence references and links.
- Workspace Evolution PDF now contains a machine-verifiable provenance appendix.
- Added Alembic migration `0010_evidence_provenance` and evidence tests.

# 0.17.0 — Sprint 16

- Analyst Verification workflow.
- Claim review audit log.
- Evidence completeness diagnostics.
- Telegram-first review commands.
- Verification PDF/JSON exports.
- Migration 0012.

# 0.17.0 — Sprint 16

- Analyst Verification workflow.
- Claim review audit log.
- Evidence completeness diagnostics.
- Telegram-first review commands.
- Verification PDF/JSON exports.
- Migration 0012.

## 0.19.0 — Sprint 18

- Added controlled external evidence acquisition worker.
- Added local-first acquisition and Workspace-scoped source plans.
- Added Telegram/RSS adapter execution with collection limits.
- Added source run, document, duplicate and error persistence.
- Added safe RSS HTTP fetcher with SSRF controls, timeout and payload limits.
- Added `retry_wait`, attempt timestamps and exponential backoff.
- Added migration `0014_controlled_external_acquisition`.
- Fixed historical Alembic link from `0004` to revision `0003`.
- 74 automated tests passing.
