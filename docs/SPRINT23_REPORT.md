# Sprint 23 — Mobile Operations

## Вердикт

Операционный путь владельца теперь рассчитан на смартфон: `Deploy → Setup → Apply migrations → Start → Status → Analyze`.

## Реализовано

- persistent `operation-state.json` в `/data/config`;
- восстановление статуса коллектора по PID после рестарта Control Center;
- idempotent start/stop/restart и запрет опасных изменений во время работы;
- статическая проверка Bot Token, API ID, API Hash, String Session и PostgreSQL URL;
- redacted events и log tail без Telegram/API/DB secrets;
- `/api/diagnostics`, `/api/errors`, `/api/update-check`;
- JSON backup/restore с SHA-256 и правами файла `0600`;
- `/api/update/prepare`: backup, безопасная остановка, подготовка к внешнему redeploy;
- мобильная Control Center-панель;
- документация фактического phone-first сценария.

Новая Alembic-миграция не добавлялась намеренно: Sprint 23 не меняет PostgreSQL-модель. Operation state относится к Control Center и должен быть доступен даже до подключения к БД, поэтому хранится в постоянном filesystem volume; `/api/migrate` по-прежнему применяет всю существующую цепочку миграций.

## Приёмка

| Проверка | Результат |
| --- | --- |
| credentials redaction | PASS |
| operation state после перезапуска Control Center | PASS |
| backup SHA-256 / restore | PASS |
| diagnostics и migration error redaction | PASS |
| targeted Ruff | PASS |
| full regression | 116 passed |
| реальный Telegram RPC | не выполнялся |
| реальный PostgreSQL/Docker/Render | внешний gate |

## Ограничения

- Проверка credentials подтверждает формат и полноту, но не выполняет реальный Telegram RPC.
- `/api/update/prepare` готовит backup и останавливает продукт; сам redeploy выполняется выбранным хостингом.
- Backup содержит секреты внутри owner-защищённого файла и должен храниться как пароль.
