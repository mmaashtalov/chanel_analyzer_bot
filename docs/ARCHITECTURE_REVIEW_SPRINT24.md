# Architecture Review before Sprint 24

## Вердикт

Sprint 24 оправдан: после Mobile Operations главный риск пилота — не отсутствие ещё одной аналитической функции, а ситуация, в которой owner видит живой Control Center или PID, хотя Telegram runtime уже остановился либо перестал отвечать.

## Scope

1. Persistent, secret-free runtime heartbeat на mounted volume.
2. Корректный lifecycle по `SIGTERM`: Telegram updater, workers, Source Registry и DB engine закрываются в определённом порядке.
3. Отделение `running` от `degraded`: PID не является единственным доказательством работоспособности.
4. Bounded auto-recovery дочернего production-процесса: backoff `5 → 15 → 45` секунд, не более трёх запусков за 15 минут.
5. Crash-loop lockout и явный ручной recovery владельца.
6. Регрессионные проверки freshness heartbeat, runtime-status, scheduling, due-recovery и lockout.

## Архитектурное решение

`runtime-health.json` находится в `/data/runtime`, отдельно от `operation-state.json` в `/data/config`.

- Runtime сам пишет heartbeat; Control Center только читает его.
- Запись не содержит Telegram token, API hash, String Session, URL БД или log payload.
- Watchdog не убивает процесс только из-за stale heartbeat: тяжёлый анализ может временно занять event loop. Он автоматически восстанавливает только подтверждённый unexpected exit.
- При restart owner намеренно переводит `desired_status` в `stopped`, поэтому watchdog не перезапускает продукт вопреки команде владельца.

## Явно отложено

- Новый пользовательский web-интерфейс: аналитический продукт остаётся Telegram-first.
- Микросервисы, Kubernetes, Redis/Celery и отдельный queue broker.
- Реальный Telegram write/RPC smoke с production credentials.
- Автоматическое убийство процесса только по stale heartbeat.
