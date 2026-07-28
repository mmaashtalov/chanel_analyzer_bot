# Chanel Analyzer Bot — Product Release

Готовая Telegram-first OSINT / Intelligence платформа с Control Center и встроенным эмулятором.

## Запуск

```bash
docker compose up -d --build
```

После запуска откройте `http://localhost:8080`, введите Telegram Bot Token, API ID, API Hash и Telethon String Session, примените миграции и нажмите «Запустить».

Эмулятор работает сразу и не требует ключей.

## Формат репозитория

Проверенный продукт хранится в `release/chanel_analyzer_bot_product_v0_22_0.tar.gz`. Dockerfile автоматически распаковывает его при сборке.

SHA-256 релиза: `da6794ad2df8a7ae26fc9fbd82207138b319e1f43fa974e1814bbaea07ab24ae`.

Версия: `0.22.0-product`. Regression: `94/94`.
