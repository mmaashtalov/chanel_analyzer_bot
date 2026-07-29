# Sprint 21 — Contradiction Triage & Resolution

## Цель

Дать владельцу Telegram-first системы управляемый способ проверить автоматически
найденное противоречие, зафиксировать решение и получить воспроизводимый след
того, почему temporal status изменился.

## Реализовано

- `ClaimContradictionRecord` — текущая очередь и её projection-state.
- `ClaimContradictionEventRecord` — append-only журнал решений с `previous_event_hash`
  и `event_hash`.
- Стабильный ID contradiction строится из Workspace, claim identity и пары claims;
  повторная сборка timeline не создаёт дубликаты очереди.
- Очередь сортируется по bounded triage priority: severity имеет больший вес,
  confidence — меньший.
- Решения аналитика:

  - `confirm_contradiction`;
  - `mark_compatible`;
  - `accept_newer`;
  - `request_evidence`.

- Для `accept_newer` система требует выбрать claim, который фактически новее по
  времени provenance bundle.
- Для `request_evidence` используется существующий evidence acquisition pipeline.
- После решения обновляются temporal status, `canonical_claim_id`, bundle metadata
  и integrity hash.
- Telegram-first команды:

  - `/contradictions WORKSPACE_ID [open|confirmed|compatible|all]`;
  - `/contradiction CONTRADICTION_ID`;
  - `/contradiction_resolve ID confirm|compatible|newer|evidence [CLAIM_ID] [комментарий]`;
  - `/contradiction_report WORKSPACE_ID [all|open]`.

- `build_contradiction_exports()` формирует JSON для машинной проверки и PDF для
  аналитического dossier.

## Миграция

`0017_contradiction_triage` продолжает `0016_temporal_claim_tracking` и добавляет:

- `claim_identities.canonical_claim_id`;
- `claim_contradictions`;
- `claim_contradiction_events`.

## Acceptance criteria

- новый contradiction получает стабильный ID;
- повторная сборка timeline сохраняет analyst resolution;
- каждое решение добавляет отдельное событие и не редактирует историю;
- `newer` невозможно применить к более старому claim;
- `request evidence` возвращает ID существующего evidence request;
- отчёт содержит queue status, rationale, resolution и историю hash-chain;
- ownership проверяется через Workspace перед чтением или изменением.

## Ограничения

Решения не делегируются LLM: классификация и переходы состояния детерминированы,
а окончательное решение принадлежит аналитику. Graph database, новый frontend и
микросервисное разделение остаются за пределами Sprint 21.
