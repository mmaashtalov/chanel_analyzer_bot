# Sprint 24 — Pilot Reliability

## Вердикт

Пилот получил независимый runtime signal и ограниченное восстановление после падения дочернего Telegram-процесса. Owner теперь видит не только PID, но и подтверждённую свежесть Telegram runtime.

## Реализовано

- `app/core/runtime.py`: persistent, atomic, `0600` heartbeat без секретов.
- `app.main`: graceful `SIGTERM`, lifecycle cleanup, heartbeat Telegram updater и двух фоновых workers.
- Worker restartability при аварийном завершении локальной task.
- `operation-state.json` schema 2: `desired_status`, recovery journal и runtime deadline.
- Watchdog Control Center: bounded recovery `5 → 15 → 45` секунд, максимум 3 попытки в 15 минут.
- Crash-loop lockout: автоматические перезапуски прекращаются, ручной `start` сбрасывает бюджет намеренно.
- `/api/status` и `/api/diagnostics`: `runtime`, `recovery`, `degraded` и redacted причины.
- Mobile Operations показывает runtime/recovery в существующей owner-панели.

## Приёмка

| Проверка | Результат |
| --- | --- |
| persistent heartbeat и права `0600` | PASS |
| stale heartbeat | PASS |
| runtime status без credentials | PASS |
| recovery scheduling | PASS |
| due-recovery | PASS |
| crash-loop lockout | PASS |
| legacy Control Center / secure proxy regression | PASS |

## Ограничения

- Реальные Telegram credentials и production PostgreSQL не использовались.
- Stale heartbeat поднимает `degraded`, но не убивает process автоматически: это защита от ложного restart во время тяжёлого анализа.
- Внешний Docker/Render gate остаётся обязательным до статуса production-ready.
