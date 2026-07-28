# Chanel Analyzer Bot — Product Release

Готовая Telegram-first OSINT / Intelligence платформа с Control Center и встроенным эмулятором.

## Запуск владельцем

### Windows

1. Установите Docker Desktop.
2. Распакуйте архив продукта.
3. Дважды нажмите `start-product.bat`.
4. Дождитесь автоматического открытия Control Center.
5. Создайте администратора и введите Telegram/API-ключи.

### Linux / macOS

```bash
chmod +x start-product.sh
./start-product.sh
```

Скрипт сам:

- проверяет Docker и Docker Compose;
- собирает и запускает сервисы;
- ждёт готовности PostgreSQL;
- проверяет `/health`;
- открывает Control Center.

Ручной технический запуск также доступен:

```bash
docker compose up -d --build
```

После запуска откройте `http://localhost:8080`. Telegram Bot Token, API ID, API Hash и Telethon String Session вводятся в Control Center. Эмулятор работает сразу и не требует ключей.

## Автоматический bootstrap

Контейнер приложения перед стартом автоматически:

- создаёт постоянные каталоги конфигурации, отчётов и runtime-данных;
- проверяет доступность записи;
- ждёт готовности PostgreSQL;
- блокирует запуск без `DATABASE_URL`;
- запускает приложение только после успешного preflight;
- публикует Docker healthcheck через `/health`.

## Конфигурация

`.env.example` содержит только параметры развёртывания. Реальные Telegram и AI-секреты не следует записывать в репозиторий: они вводятся через мастер Control Center.

## Формат репозитория

Проверенный продукт хранится в `release/chanel_analyzer_bot_product_v0_22_0.tar.gz`. Dockerfile автоматически распаковывает его при сборке.

SHA-256 релиза: `da6794ad2df8a7ae26fc9fbd82207138b319e1f43fa974e1814bbaea07ab24ae`.

Версия: `0.22.0-product`. Regression: `94/94`.

<!-- production-owner-gate -->
## Запуск с телефона

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/mmaashtalov/chanel_analyzer_bot)

1. Нажмите **Deploy to Render** и задайте `OWNER_GATE_PASSWORD`.
2. После развёртывания откройте адрес сервиса. Логин внешнего owner-gate: `owner`, пароль — заданный при deploy.
3. В Control Center создайте внутреннего администратора, введите Telegram-ключи и параметры источников, запустите проверки и нажмите **Запустить продукт**.
4. Публичный эмулятор работает без ключей: https://mmaashtalov.github.io/chanel_analyzer_bot/

`/health`, `/ready` и `/emulator` доступны публично. Control Center и управляющие API защищены внешним owner-gate и внутренней сессией администратора.
