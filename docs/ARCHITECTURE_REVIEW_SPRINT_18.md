# Architecture Review перед Sprint 18

## Вердикт

Sprint 18 допустим только как controlled external acquisition worker.

Confidence: высокий.

## Причина

Sprint 17 организует request lifecycle и закрывает gaps документами, уже присутствующими в локальном хранилище. Следующий объективный разрыв — выполнение сетевого дозапроса через существующие adapters, когда local-first linking не дал результата.

## Разрешённый объём

1. Worker получает queued evidence requests.
2. Применяет source plan и существующий SourceRegistry.
3. Ограничивает дату, объём и число повторов.
4. Сохраняет документы через единый ingestion-контур.
5. Повторно запускает document linking.
6. Не допускает бесконечных retries.
7. Показывает прогресс и ошибки в Telegram.

## Запрещённая сложность

- новый crawler framework;
- Kubernetes;
- отдельный микросервис на каждый источник;
- автономное расширение Workspace без решения аналитика;
- LLM-генерация поисковых запросов без детерминированного fallback;
- массовый сбор вне source plan.
