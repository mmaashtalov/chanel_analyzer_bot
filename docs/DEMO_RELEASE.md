# Demo Release

## Цель

Показать полный аналитический workflow стороннему наблюдателю без передачи Telegram API credentials или пользовательской MTProto-сессии.

## Что демонстрируется

1. Workspace Evolution.
2. Claims и evidence quality.
3. Первичные Telegram/RSS документы.
4. Integrity hash provenance bundle.
5. Analyst Verification.
6. Evidence Acquisition.
7. Source Independence.
8. Temporal Claim Timeline.

## Локальный запуск

```bash
docker compose -f docker-compose.demo.yml up --build
```

Открыть `http://localhost:8000`.

Проверка: `http://localhost:8000/health`.

## Облачный запуск

Репозиторий содержит `render.yaml`. После подключения GitHub-репозитория к Render сервис собирается из Dockerfile и запускается с `APP_MODE=demo`.

Demo-mode не требует:

- Telegram Bot Token;
- Telegram API ID/API Hash;
- MTProto String Session;
- PostgreSQL;
- внешнего LLM.

## Production-mode

Production остаётся отдельным режимом:

```bash
APP_MODE=production python -m app.entrypoint
```

Он использует Telegram, PostgreSQL, workers и реальные adapters.


## Demo Hardening 0.21.2

Добавлены:

- `GET /ready` — readiness с полной проверкой артефактов;
- `GET /api/self-test` — подробный отчёт по каждому JSON/PDF;
- SHA-256 артефактов;
- пошаговый guided demo на главной странице;
- fail-closed readiness: отсутствие или повреждение обязательного файла возвращает HTTP 503.

Рекомендуемый порядок демонстрации:

1. Открыть главную страницу и показать KPI.
2. Нажимать «Запустить пошаговый показ» шесть раз.
3. Открыть self-test и показать статус `ok`.
4. Открыть provenance PDF и timeline PDF.
5. Завершить демонстрацию объяснением различия demo-mode и production-mode.
