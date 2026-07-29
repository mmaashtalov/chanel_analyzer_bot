# Architecture Review перед Sprint 19

## Вердикт

Следующий спринт должен усиливать качество evidence, а не расширять число источников.

Confidence: высокий.

## Подтверждённый разрыв

Sprint 18 умеет собирать и связывать документы, но `resolved` сейчас определяется преимущественно наличием нескольких source types. Это недостаточно для профессиональной Intelligence-оценки: два источника могут быть зависимыми, перепечатывать один материал или ссылаться на общий первоисточник.

## Рекомендуемый Sprint 19

**Source Independence & Corroboration Engine**

1. source lineage и upstream URL;
2. cross-source content similarity;
3. duplicate narrative clusters;
4. independence score;
5. corroboration score claim;
6. downgrade `resolved` при псевдонезависимых источниках;
7. Telegram explanation;
8. PDF/JSON provenance update;
9. migration и tests.

## Не делать

- новые adapters;
- crawling всего web;
- LLM-only independence assessment;
- микросервисное дробление;
- отдельный frontend.
