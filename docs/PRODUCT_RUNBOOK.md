# Product Runbook 0.24.0 — Production Readiness

## Текущий режим без реальных ключей

До финального запуска продукт разворачивается в `APP_MODE=setup`. Control Center, owner-gate, PostgreSQL, миграции, backup/restore, diagnostics и Emulator 4.0 проверяются без Telegram Bot Token, API ID/API Hash и Telethon StringSession.

Отсутствие Telegram-ключей в этом режиме является ожидаемым состоянием, а не ошибкой инфраструктуры. Основной production runtime не должен запускаться, пока Control Center не подтвердит полную конфигурацию.

## Финальный сценарий владельца

1. Выполнить Deploy в Render по Blueprint.
2. Задать только обязательный `OWNER_GATE_PASSWORD` в форме Render.
3. Открыть Control Center со смартфона через HTTPS и войти как `owner`.
4. Убедиться, что PostgreSQL создан, pre-deploy миграция завершилась и `/health` отвечает.
5. В самый последний момент ввести Bot Token, API ID, API Hash и Telethon StringSession.
6. Выполнить статическую проверку credentials и сохранить конфигурацию.
7. Нажать «Применить миграции» и дождаться `applied`.
8. Нажать «Запустить продукт» и дождаться одновременно `running` и `runtime=healthy`.
9. Открыть Telegram-бота и выполнить `/start`, затем `/analyze @channel`.

После Deploy для ежедневной эксплуатации не требуются SSH, локальный Docker или ПК.

## Автоматические production-проверки

CI обязан подтвердить:

- воспроизводимость release archive и `MANIFEST.json`;
- отсутствие `.env`, settings и operation-state в Git;
- полный pytest regression;
- Python compile и Ruff для production-интеграции;
- PostgreSQL 17 с pgvector;
- применение всей Alembic-цепочки до единственной head `0018`;
- Docker build из текущего дерева;
- HTTP smoke-test demo-режима;
- публичный `/health` через owner-gate;
- `401` на защищённый Control Center без Basic Auth;
- доступ владельца с корректным Basic Auth;
- безопасный setup-статус `configured=false` без Telegram-ключей.

## Диагностика

- Control Center не открывается: проверить Render deploy logs и `/health`.
- БД не готова: проверить статус managed Postgres и `DATABASE_URL` в Render.
- Миграция не проходит: проверить pre-deploy logs; URL автоматически нормализуется в `postgresql+asyncpg://`.
- Бот сразу остановился: открыть события Control Center и redacted log tail.
- Эмулятор не готов: открыть `/api/self-test`.
- Статус `error`: открыть «Диагностика», затем `/api/errors`; секреты в ответе должны отсутствовать.
- Статус `degraded` или `runtime=stale`: дождаться следующего heartbeat; если состояние не меняется — выполнить ручной restart.
- `auto_recovery` запланирован: не запускать несколько ручных restart параллельно.
- `auto_recovery` остановлен: устранить причину после crash-loop lockout, затем выполнить ручной старт.

## Backup и восстановление

Перед обновлением:

1. Остановить основной runtime либо нажать «Подготовить безопасное обновление».
2. Скачать owner-защищённый JSON backup и сохранить его как пароль.
3. Для БД использовать managed backup/PITR Render либо отдельный `pg_dump` при локальном Docker.
4. После restore повторно применить миграции и проверить diagnostics до запуска Telegram runtime.

## Rollback

При неудачном deploy:

1. Не вводить или не менять Telegram-ключи.
2. Оставить основной runtime остановленным.
3. Выполнить rollback на предыдущий успешный Render deploy.
4. Проверить `/health`, `/ready`, owner-gate и состояние PostgreSQL.
5. Восстановить owner backup только при подтверждённой потере `/data`.

## Финальный внешний gate

Автоматизация не может заменить только четыре проверки с реальными данными:

- Telegram Bot Token принимает запросы;
- Telethon StringSession читает разрешённый канал;
- PDF/JSON фактически доставляются ботом;
- длительный monitoring получает обновления и отправляет alert.

До этого момента статус проекта: **production-ready code and infrastructure, credentials pending**.
