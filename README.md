# Chanel Analyzer Bot — Product Release 0.24.0

Готовая Telegram-first OSINT / Intelligence платформа. Аналитическая работа выполняется в Telegram; Control Center остаётся только owner-контуром развёртывания и восстановления.

## Статус production readiness

Исходники, PostgreSQL/pgvector, Alembic, Docker, owner-gate, Control Center, backup/restore, diagnostics и recovery-контур проверяются автоматически без реальных Telegram-ключей. Bot Token, API ID/API Hash и Telethon StringSession намеренно вводятся только в последний момент через owner-защищённый Control Center.

Render Blueprint создаёт платный web service с persistent disk и отдельный managed PostgreSQL в регионе Frankfurt. Бесплатные Render-инстансы не используются как production-конфигурация.

Подробный порядок запуска, rollback и финальный credential gate описаны в `docs/PRODUCT_RUNBOOK.md`.

## Запуск владельцем с телефона

### Render

1. Выполните Deploy по кнопке ниже.
2. Задайте обязательный `OWNER_GATE_PASSWORD`; Telegram-ключи на этом этапе не нужны.
3. Дождитесь создания managed PostgreSQL и успешной pre-deploy миграции.
4. Откройте публичный URL Control Center со смартфона.
5. В последний момент введите Telegram credentials, проверьте и сохраните конфигурацию.
6. Нажмите «Применить миграции», затем «Запустить продукт».
7. Откройте Telegram-бота и выполните `/analyze @channel`.

После Deploy для ежедневной эксплуатации не требуются SSH, локальный Docker или ПК.

### Локальный Docker-вариант

1. Установите Docker Desktop.
2. Распакуйте архив продукта.
3. Дважды нажмите `start-product.bat` либо запустите `./start-product.sh`.
4. Откройте Control Center на смартфоне в локальной сети.

Для Linux / macOS:

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

Ручной технический запуск:

```bash
docker compose up -d --build
```

После запуска откройте `http://localhost:8080`. Telegram Bot Token, API ID, API Hash и Telethon String Session вводятся в Control Center. Эмулятор работает сразу и не требует ключей.

## Автоматический bootstrap и Mobile Operations

Контейнер приложения перед стартом автоматически:

- создаёт постоянные каталоги конфигурации, отчётов и runtime-данных;
- проверяет доступность записи;
- ждёт готовности PostgreSQL;
- блокирует запуск без `DATABASE_URL`;
- запускает приложение только после успешного preflight;
- публикует Docker healthcheck через `/health`.

## Конфигурация

`.env.example` содержит только параметры развёртывания. Реальные Telegram и AI-секреты нельзя записывать в репозиторий: они вводятся через мастер Control Center.

Control Center сохраняет operation state в постоянном `/data` volume. Поэтому после рестарта хостинга владелец видит фактический статус коллектора, последнюю миграцию, последнюю ошибку и историю операций.

## Надёжность пилота

- Production runtime пишет secret-free heartbeat в `/data/runtime/runtime-health.json`; owner-контур отличает живой Telegram polling от одного только PID процесса.
- `SIGTERM` переводит бот в корректное завершение: останавливаются updater и workers, закрываются источники и соединения БД.
- При неожиданном выходе дочернего процесса Control Center делает до трёх автоматических перезапусков за 15 минут с backoff `5 → 15 → 45` секунд.
- После исчерпания лимита включается защита от crash-loop: новый запуск выполняется только вручную, причина видна в Diagnostics.
- Статусы `runtime=stale/error` означают, что PID сам по себе не считается подтверждением работоспособности; требуется проверить owner Diagnostics.

Доступны owner-защищённые операции:

- `/api/credentials/check` — статическая проверка обязательных полей без Telegram RPC;
- `/api/migrate`, `/api/start`, `/api/stop`, `/api/restart` — lifecycle;
- `/api/diagnostics` и `/api/errors` — диагностика и redacted log tail;
- `/api/backup` и `/api/restore` — JSON backup с SHA-256;
- `/api/update/prepare` — backup и безопасная остановка перед redeploy.

## Формат репозитория

Проверенный продукт хранится в `release/chanel_analyzer_bot_product_v0_24_0.tar.gz`. Dockerfile собирает текущее дерево репозитория напрямую.

SHA-256 релиза фиксируется в `MANIFEST.json` после воспроизводимой сборки архива.

Версия: `0.24.0-product`. Regression-счётчик вычисляется из `MANIFEST.json`.

<!-- production-owner-gate -->
## Быстрые ссылки

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/mmaashtalov/chanel_analyzer_bot)

Публичный мобильный эмулятор без ключей:
https://raw.githack.com/mmaashtalov/chanel_analyzer_bot/main/emulator/index.html

`/health`, `/ready` и `/emulator` доступны публично. Control Center и управляющие API защищены внешним owner-gate и внутренней сессией администратора.
