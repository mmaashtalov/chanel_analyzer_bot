# Product Runbook 0.22.0

## Сценарий владельца

1. Запустить `docker compose up -d --build`.
2. Открыть Control Center на порту 8080.
3. Сначала открыть вкладку «Эмулятор» и пройти демонстрационный сценарий.
4. В «Настройка» ввести Telegram credentials и String Session.
5. Сохранить конфигурацию.
6. Нажать «Применить миграции».
7. Нажать «Запустить».
8. Проверить статус `running` и открыть Telegram-бота.

## Диагностика

- Control Center не открывается: `docker compose ps`, затем `docker compose logs app`.
- БД не готова: `docker compose logs db`.
- Миграция не проходит: проверить PostgreSQL URL и пароль.
- Бот сразу остановился: открыть события Control Center и `docker compose logs app`.
- Эмулятор не готов: открыть `/api/self-test`.

## Backup

```bash
docker compose exec db pg_dump -U postgres osint > backup.sql
```

Конфигурация находится в Docker volume `product_config`; резервное копирование volume необходимо выполнять средствами Docker/хостинга.
