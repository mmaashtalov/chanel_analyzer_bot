# Product Runbook 0.24.0 — Pilot Reliability

## Сценарий владельца

1. Выполнить Deploy в Render или запустить `docker compose up -d --build` на хосте.
2. Открыть Control Center со смартфона.
3. Проверить формат Bot Token, API ID, API Hash, String Session и PostgreSQL URL.
4. Сохранить конфигурацию.
5. Нажать «Применить миграции» и дождаться `applied`.
6. Нажать «Запустить продукт» и дождаться `running` вместе с `runtime=healthy`.
7. Открыть Telegram-бота и выполнить `/analyze @channel`.

В рабочем режиме SSH и локальный Docker не нужны. После рестарта хостинга Control Center восстанавливает operation state из `/data/config/operation-state.json`, перепроверяет PID коллектора и читает secret-free heartbeat из `/data/runtime/runtime-health.json`.

## Диагностика

- Control Center не открывается: `docker compose ps`, затем `docker compose logs app`.
- БД не готова: `docker compose logs db`.
- Миграция не проходит: проверить PostgreSQL URL и пароль.
- Бот сразу остановился: открыть события Control Center и `docker compose logs app`.
- Эмулятор не готов: открыть `/api/self-test`.
- Статус `error`: открыть «Диагностика», затем `/api/errors`; секреты в ответе должны отсутствовать.
- Статус `degraded` или `runtime=stale`: PID не доказывает исправность Telegram-контра. Открыть «Диагностика», дождаться следующего heartbeat; если состояние не меняется — выполнить ручной restart.
- `auto_recovery` запланирован: дождаться одной ограниченной попытки (`5 → 15 → 45` секунд). Не запускать несколько ручных restart параллельно.
- `auto_recovery` остановлен: сработала защита от crash-loop после 3 попыток за 15 минут. Сначала устранить причину в redacted diagnostics, затем нажать «Запустить продукт» вручную.
- Обновление: сначала нажать «Подготовить безопасное обновление», скачать backup и только затем выполнить Redeploy.

## Backup

```bash
docker compose exec db pg_dump -U postgres osint > backup.sql
```

Конфигурация находится в Docker volume `product_config` или `/data` на Render. Для прикладного backup используйте кнопку «Скачать backup»: файл содержит секреты и должен храниться как пароль. После восстановления обязательно повторно примените миграции.
