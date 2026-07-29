# Sprint 18 — Controlled External Acquisition Worker

## Версия

`0.19.0`

## Architecture Review

Sprint одобрен, поскольку закрывает подтверждённый разрыв Sprint 17: evidence request существовал, но не мог контролируемо собирать отсутствующие документы через уже реализованные adapters.

Новые микросервисы, crawler framework, web UI и LLM не добавлялись.

## Реализовано

1. `ControlledExternalAcquisition`:
   - local-first lookup;
   - сбор только по source plan Workspace;
   - ограничение источников, периода, документов и timeout;
   - повторный linking;
   - финализация request.
2. `EvidenceAcquisitionWorker`:
   - polling due requests;
   - обработка `queued` и `retry_wait`;
   - корректная остановка приложения.
3. `SourceCollectionRepository`:
   - source registry persistence;
   - source runs;
   - accepted/duplicate counters;
   - source errors.
4. Безопасный RSS fetcher:
   - только HTTP/HTTPS;
   - запрет private, loopback, link-local, multicast, reserved и unspecified addresses;
   - проверка redirects;
   - timeout и payload-size limit.
5. Retry policy:
   - `retry_wait`;
   - `last_attempt_at`;
   - `next_attempt_at`;
   - экспоненциальный backoff;
   - max attempts.
6. Исправлена старая Alembic-ссылка `0004 → 0003`.

## Миграция

`0014_controlled_external_acquisition`

Добавлены поля:

- `collection_summary_json`;
- `last_attempt_at`;
- `next_attempt_at`.

## Валидация

- `compileall`: успешно;
- pytest: 74/74;
- migration head: `0014_controlled_external_acquisition`;
- `ruff`: не запускался, пакет отсутствовал в среде сборки.

## Ограничения

- external acquisition поддерживает только adapters, зарегистрированные в `SourceRegistry`;
- в Sprint 18 фактически включены Telegram и RSS;
- RSS safety снижает SSRF-риск, но production deployment всё равно должен применять egress policy;
- автоматическая оценка независимости источников пока базовая.
