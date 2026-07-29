# Sprint 17 — Evidence Acquisition Orchestration

## Версия

0.18.0

## Реализовано

- Evidence Request как отдельная доменная сущность.
- Lifecycle: queued → collecting/linking → resolved/partial/failed/cancelled.
- Автоматический план источников из Workspace.
- Поисковые термины из claim statement и assessment.
- Защита от дублирования активных запросов.
- Лимит повторов.
- Hash-аудит каждого перехода статуса.
- Local-first linking: перед внешним сбором проверяется локальное хранилище документов.
- Добавление document-level evidence к claim.
- Пересчёт evidence quality, completeness и integrity hash.
- Telegram-команды управления.

## Telegram-команды

- `/evidence_request WORKSPACE_ID CLAIM_ID`
- `/evidence_requests [WORKSPACE_ID]`
- `/evidence_request_run REQUEST_ID`
- `/evidence_request_retry REQUEST_ID`
- `/evidence_request_cancel REQUEST_ID`
- `/evidence_request_history REQUEST_ID`

## Миграция

`0013_evidence_acquisition`

## Валидация

- Python compileall: passed.
- Pytest: 67 passed.
- Легаси не включён.
