from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from app.evolution.models import ChangeSeverity, EvolutionEvent, EvolutionReport
from app.profiles.models import IntelligenceProfile

_METRIC_LABELS = {
    "posts_count": "Количество публикаций",
    "posts_per_day": "Публикаций в сутки",
    "mean_views": "Средний охват",
    "median_views": "Медианный охват",
    "mean_reactions": "Среднее число реакций",
    "mean_forwards": "Среднее число пересылок",
    "mean_post_length": "Средняя длина публикации",
    "engagement_per_1000_views": "Вовлечённость на 1000 просмотров",
    "median_interval_hours": "Медианный интервал между публикациями",
}

_DNA_LABELS = {
    "lexical_diversity": "Лексическое разнообразие",
    "mean_sentence_length": "Средняя длина предложения",
    "mean_paragraphs": "Абзацная структура",
    "uppercase_ratio": "Доля верхнего регистра",
    "emoji_rate": "Использование эмодзи",
    "question_rate": "Частота вопросов",
    "exclamation_rate": "Эмоциональная пунктуация",
    "ellipsis_rate": "Использование многоточий",
    "dash_rate": "Использование тире",
    "link_rate": "Ссылочность",
    "direct_address_rate": "Прямое обращение к аудитории",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _relative_delta(old: float, new: float) -> float:
    if abs(old) < 1e-9:
        return 1.0 if abs(new) > 1e-9 else 0.0
    return (new - old) / abs(old)


def _severity(relative: float, absolute: float, category: str) -> ChangeSeverity:
    magnitude = max(abs(relative), abs(absolute))
    if category in {"narrative", "source"} and magnitude >= 0.55:
        return ChangeSeverity.CRITICAL
    if magnitude >= 0.50:
        return ChangeSeverity.HIGH
    if magnitude >= 0.25:
        return ChangeSeverity.MEDIUM
    return ChangeSeverity.LOW


def _confidence(previous: IntelligenceProfile, current: IntelligenceProfile, signal: float) -> float:
    sample_factor = min(1.0, min(previous.source_post_count, current.source_post_count) / 60.0)
    base = min(previous.confidence, current.confidence)
    return round(max(0.15, min(0.99, base * (0.65 + 0.35 * sample_factor) * (0.8 + 0.2 * min(1.0, signal)))), 4)


def _metric_events(previous: IntelligenceProfile, current: IntelligenceProfile) -> list[EvolutionEvent]:
    events: list[EvolutionEvent] = []
    for key, label in _METRIC_LABELS.items():
        old, new = _number(previous.metrics.get(key)), _number(current.metrics.get(key))
        if old is None or new is None:
            continue
        relative = _relative_delta(old, new)
        if abs(relative) < 0.15:
            continue
        severity = _severity(relative, 0.0, "metrics")
        direction = "вырос" if relative > 0 else "снизился"
        events.append(EvolutionEvent(
            event_type="metric_shift",
            category="metrics",
            title=f"{label}: {direction}",
            description=f"Показатель изменился с {old:.2f} до {new:.2f} ({relative:+.0%}).",
            severity=severity,
            confidence=_confidence(previous, current, abs(relative)),
            old_value=old,
            new_value=new,
            delta=relative,
        ))
    return events


def _dna_events(previous: IntelligenceProfile, current: IntelligenceProfile) -> list[EvolutionEvent]:
    events: list[EvolutionEvent] = []
    for key, label in _DNA_LABELS.items():
        old, new = _number(previous.content_dna.get(key)), _number(current.content_dna.get(key))
        if old is None or new is None:
            continue
        relative, absolute = _relative_delta(old, new), new - old
        if abs(relative) < 0.20 and abs(absolute) < 0.08:
            continue
        severity = _severity(relative, absolute, "style")
        direction = "усилилось" if new > old else "ослабло"
        events.append(EvolutionEvent(
            event_type="content_dna_shift",
            category="style",
            title=f"{label}: {direction}",
            description=f"Признак изменился с {old:.3f} до {new:.3f}.",
            severity=severity,
            confidence=_confidence(previous, current, max(abs(relative), abs(absolute))),
            old_value=old,
            new_value=new,
            delta=relative,
            evidence=tuple(_trait_evidence(current.content_dna, key)),
        ))
    return events


def _trait_evidence(content_dna: dict[str, Any], trait_name: str) -> Iterable[int]:
    for trait in content_dna.get("traits", []):
        if not isinstance(trait, dict):
            continue
        if str(trait.get("name", "")).casefold() not in {trait_name.casefold(), _DNA_LABELS.get(trait_name, "").casefold()}:
            continue
        for item in trait.get("evidence", []):
            if isinstance(item, dict) and isinstance(item.get("message_id"), int):
                yield item["message_id"]


def _top_terms(profile: IntelligenceProfile, limit: int = 20) -> set[str]:
    candidates = (
        profile.metrics.get("top_terms")
        or profile.metrics.get("frequent_terms")
        or profile.metrics.get("semantic", {}).get("top_terms", [])
    )
    terms: list[str] = []
    for item in candidates or []:
        if isinstance(item, str):
            terms.append(item.casefold())
        elif isinstance(item, (list, tuple)) and item:
            terms.append(str(item[0]).casefold())
        elif isinstance(item, dict) and item.get("term"):
            terms.append(str(item["term"]).casefold())
    return set(terms[:limit])


def _narrative_events(previous: IntelligenceProfile, current: IntelligenceProfile) -> list[EvolutionEvent]:
    old_terms, new_terms = _top_terms(previous), _top_terms(current)
    if not old_terms or not new_terms:
        return []
    added, removed = sorted(new_terms - old_terms), sorted(old_terms - new_terms)
    union = old_terms | new_terms
    overlap = len(old_terms & new_terms) / len(union) if union else 1.0
    events: list[EvolutionEvent] = []
    if overlap < 0.60:
        severity = ChangeSeverity.CRITICAL if overlap < 0.35 else ChangeSeverity.HIGH
        events.append(EvolutionEvent(
            event_type="narrative_shift",
            category="narrative",
            title="Изменилось тематическое ядро",
            description=(f"Сходство набора ведущих терминов составляет {overlap:.0%}. "
                         f"Новые: {', '.join(added[:8]) or 'нет'}; исчезли: {', '.join(removed[:8]) or 'нет'}."),
            severity=severity,
            confidence=_confidence(previous, current, 1.0 - overlap),
            old_value=sorted(old_terms),
            new_value=sorted(new_terms),
            delta=overlap - 1.0,
        ))
    elif added:
        events.append(EvolutionEvent(
            event_type="new_topics",
            category="narrative",
            title="Появились новые устойчивые темы",
            description=f"Новые термины: {', '.join(added[:8])}.",
            severity=ChangeSeverity.MEDIUM,
            confidence=_confidence(previous, current, len(added) / max(1, len(new_terms))),
            old_value=[],
            new_value=added[:8],
        ))
    return events


def _vector_shift(previous: IntelligenceProfile, current: IntelligenceProfile, name: str, category: str) -> EvolutionEvent | None:
    old_vector = getattr(previous, name)
    new_vector = getattr(current, name)
    if not old_vector or len(old_vector) != len(new_vector):
        return None
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(old_vector, new_vector))) / math.sqrt(len(old_vector))
    if distance < 0.12:
        return None
    labels = {
        "temporal_vector": "Изменился публикационный ритм",
        "structural_vector": "Изменилась структура публикаций",
        "style_vector": "Изменился редакционный стиль",
    }
    return EvolutionEvent(
        event_type=f"{category}_vector_shift",
        category=category,
        title=labels[name],
        description=f"Нормированная дистанция между версиями: {distance:.3f}.",
        severity=_severity(distance, distance, category),
        confidence=_confidence(previous, current, distance),
        old_value="previous_vector",
        new_value="current_vector",
        delta=distance,
    )


def compare_profile_versions(
    previous: IntelligenceProfile,
    current: IntelligenceProfile,
    from_version: int,
    to_version: int,
) -> EvolutionReport:
    if previous.username != current.username:
        raise ValueError("Evolution Engine сравнивает версии одного канала")
    events = _metric_events(previous, current)
    events.extend(_dna_events(previous, current))
    events.extend(_narrative_events(previous, current))
    for vector_name, category in (
        ("style_vector", "style"),
        ("temporal_vector", "temporal"),
        ("structural_vector", "structure"),
    ):
        event = _vector_shift(previous, current, vector_name, category)
        if event is not None:
            events.append(event)
    rank = {ChangeSeverity.CRITICAL: 4, ChangeSeverity.HIGH: 3, ChangeSeverity.MEDIUM: 2, ChangeSeverity.LOW: 1}
    events.sort(key=lambda item: (rank[item.severity], item.confidence, abs(item.delta or 0.0)), reverse=True)
    summary = tuple(event.title for event in events[:5]) or ("Значимых изменений между версиями не обнаружено",)
    confidence = round(sum(event.confidence for event in events) / len(events), 4) if events else round(min(previous.confidence, current.confidence), 4)
    return EvolutionReport(previous.username, from_version, to_version, confidence, tuple(events), summary)
