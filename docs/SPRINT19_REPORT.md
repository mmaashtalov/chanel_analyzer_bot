# Sprint 19 Report

Версия: 0.20.0.

Реализован детерминированный Source Independence & Corroboration Engine. Несколько публикаций больше не считаются независимыми только из-за разных source_type. Документы кластеризуются по идентичному содержанию, fingerprint, upstream-домену и высокой текстовой схожести. Claim получает independence score, corroboration score и объяснимые кластеры.

Миграция: 0015_source_independence.

Тесты: 78/78.
