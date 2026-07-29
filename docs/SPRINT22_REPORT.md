# Sprint 22 — Unified Evidence-First Analyze

## Цель

Соединить пользовательскую команду `/analyze` с уже существующим Source Registry и evidence-контуром. Один запуск должен формировать воспроизводимый пакет, а не только PDF с метриками.

## Реализовано

- Telegram snapshot преобразуется в `UnifiedDocument` один раз и используется одновременно для расчётов и сохранения источника.
- Source Registry возвращает карту `external_document_id → source_documents.id`; повторные документы отмечаются как duplicates.
- Для анализа сохраняются snapshot evidence, calculation evidence и primary-document evidence с excerpt, fingerprint, URL, автором и датой публикации.
- Claims связаны с evidence IDs; bundle имеет детерминированные IDs и SHA-256 integrity hash.
- PDF содержит provenance appendix; JSON содержит claims, evidence, limitations, coverage и operational metadata.
- Bundle связывается со всеми активными Workspace владельца, где канал добавлен как `channel`.
- Review и temporal pipeline включают такие bundles через явные `workspace_provenance_links`.

## Приёмка

| Проверка | Результат |
| --- | --- |
| Один provider fetch на `/analyze` | PASS |
| Source Registry и evidence используют один snapshot | PASS |
| Повторяемые bundle/claim/evidence IDs | PASS |
| PDF + полный JSON | PASS |
| Empty input и ограничения | PASS |
| Workspace link идемпотентен | PASS |
| Полный regression | 111 passed |
| `compileall`, Ruff, preflight, manifest | PASS |

## Ограничения

- Реальная Telegram-сессия и длительный сбор production-каналов ещё не проверены.
- LLM не используется как источник истины; claims строятся детерминированными расчётами.
- Operational metadata содержит ID запуска, поэтому полностью идентичны именно логический bundle, evidence IDs и integrity hash, а не все поля JSON.
