# Architecture Review перед Sprint 20

## Вердикт

Sprint 20 допустим только как Temporal Claim Tracking & Contradiction Resolution.

## Причина

После оценки независимости следующий реальный разрыв — одинаковое утверждение может меняться во времени, а противоречащие документы сейчас не образуют управляемый lifecycle.

## Разрешённый состав

1. stable claim identity между snapshots;
2. claim timeline;
3. superseded/contradicted status;
4. связь нового claim с предыдущим;
5. contradiction evidence;
6. Telegram timeline;
7. PDF/JSON history;
8. миграция и тесты.

## Не требуется

- новая БД графов;
- новый frontend;
- LLM-only contradiction detection;
- микросервисы.
