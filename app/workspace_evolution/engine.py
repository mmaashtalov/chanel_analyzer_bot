from __future__ import annotations

from datetime import datetime
from typing import Any

from app.workspace_evolution.models import EvolutionObservation, WorkspaceEvolutionReport, WorkspaceTrend

_SEVERITY = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _pairs(value: Any) -> dict[str, int]:
    return {str(k): int(v) for k, v in (value or [])}


def _pct(old: float | int | None, new: float | int | None) -> float | None:
    if old is None or new is None:
        return None
    old_f, new_f = float(old), float(new)
    if old_f == 0:
        return 0.0 if new_f == 0 else 1.0
    return (new_f - old_f) / abs(old_f)


def _delta_sets(old: dict[str, int], new: dict[str, int]) -> tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]:
    added = tuple(sorted(((k, v) for k, v in new.items() if k not in old), key=lambda x: (-x[1], x[0].casefold())))
    removed = tuple(sorted(((k, v) for k, v in old.items() if k not in new), key=lambda x: (-x[1], x[0].casefold())))
    return added, removed


def compare_workspace_snapshots(
    *,
    workspace_name: str,
    baseline_snapshot_id: str,
    current_snapshot_id: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> WorkspaceEvolutionReport:
    old_entities, new_entities = _pairs(baseline.get("top_entities")), _pairs(current.get("top_entities"))
    old_domains, new_domains = _pairs(baseline.get("top_domains")), _pairs(current.get("top_domains"))
    old_keywords, new_keywords = _pairs(baseline.get("top_keywords")), _pairs(current.get("top_keywords"))
    added_entities, removed_entities = _delta_sets(old_entities, new_entities)
    added_domains, removed_domains = _delta_sets(old_domains, new_domains)
    added_keywords, removed_keywords = _delta_sets(old_keywords, new_keywords)

    old_alerts = {str(k): int(v) for k, v in (baseline.get("alert_counts") or {}).items()}
    new_alerts = {str(k): int(v) for k, v in (current.get("alert_counts") or {}).items()}
    alert_delta = {key: new_alerts.get(key, 0) - old_alerts.get(key, 0) for key in sorted(set(old_alerts) | set(new_alerts))}

    metric_deltas: dict[str, float | int | None] = {
        "total_posts_absolute": int(current.get("total_posts", 0)) - int(baseline.get("total_posts", 0)),
        "total_posts_percent": _pct(baseline.get("total_posts"), current.get("total_posts")),
        "coverage_ratio": float(current.get("coverage_ratio", 0)) - float(baseline.get("coverage_ratio", 0)),
        "weighted_confidence": float(current.get("weighted_confidence", 0)) - float(baseline.get("weighted_confidence", 0)),
        "mean_views_percent": _pct(baseline.get("mean_views"), current.get("mean_views")),
        "engagement_percent": _pct(baseline.get("mean_engagement_per_1000"), current.get("mean_engagement_per_1000")),
        "activity_percent": _pct(baseline.get("mean_posts_per_day"), current.get("mean_posts_per_day")),
    }

    observations: list[EvolutionObservation] = []
    posts_pct = metric_deltas["total_posts_percent"]
    important_alert_delta = alert_delta.get("high", 0) + alert_delta.get("critical", 0)
    if isinstance(posts_pct, float) and abs(posts_pct) >= 0.15:
        direction = "вырос" if posts_pct > 0 else "снизился"
        observations.append(EvolutionObservation(
            "activity", "high" if abs(posts_pct) >= 0.5 else "medium",
            f"Объём публикаций {direction} на {abs(posts_pct):.0%}.",
            (f"Было: {baseline.get('total_posts', 0)}", f"Стало: {current.get('total_posts', 0)}"),
            min(0.98, 0.7 + abs(posts_pct) / 3),
            "Изменение указывает на сдвиг интенсивности информационной активности, но не объясняет его причину.",
        ))
    if important_alert_delta > 0:
        observations.append(EvolutionObservation(
            "alerts", "high" if important_alert_delta >= 3 else "medium",
            "Количество High/Critical сигналов увеличилось.",
            (f"Изменение: +{important_alert_delta}",),
            0.9,
            "Наблюдается эскалация значимых изменений; требуется проверка первичных публикаций.",
        ))
    if added_entities:
        observations.append(EvolutionObservation(
            "entities", "medium", f"В информационное поле вошли новые сущности: {len(added_entities)}.",
            tuple(name for name, _ in added_entities[:10]), min(0.95, 0.65 + len(added_entities) / 50),
            "Появление новых сущностей может отражать расширение повестки или новый сюжет.",
        ))
    if added_domains:
        observations.append(EvolutionObservation(
            "domains", "medium" if len(added_domains) >= 2 else "low",
            f"Выявлены новые внешние домены: {len(added_domains)}.",
            tuple(name for name, _ in added_domains[:10]), 0.8,
            "Источникоснабжение контура изменилось; это не доказывает аффилированность или координацию.",
        ))
    if added_keywords:
        observations.append(EvolutionObservation(
            "narrative", "high" if len(added_keywords) >= 4 else "medium",
            f"Появились новые ключевые темы: {len(added_keywords)}.",
            tuple(name for name, _ in added_keywords[:10]), 0.78,
            "Есть признаки тематического дрейфа; вывод ограничен набором ключевых слов Workspace.",
        ))
    coverage_delta = float(metric_deltas["coverage_ratio"] or 0)
    if coverage_delta < -0.1:
        observations.append(EvolutionObservation(
            "coverage", "high", "Покрытие аналитическими данными ухудшилось.",
            (f"Изменение покрытия: {coverage_delta:.0%}",), 1.0,
            "Сравнение может быть искажено из-за снижения числа доступных профилей.",
        ))

    structural_changes = len(added_entities) + len(removed_entities) + len(added_domains) + len(removed_domains)
    if coverage_delta < -0.2:
        trend = WorkspaceTrend.INSUFFICIENT_DATA
    elif important_alert_delta >= 3 and isinstance(posts_pct, float) and posts_pct >= 0.2:
        trend = WorkspaceTrend.ESCALATING
    elif structural_changes >= 10 and len(added_keywords) >= 3:
        trend = WorkspaceTrend.MAJOR_SHIFT
    elif len(added_keywords) >= 3:
        trend = WorkspaceTrend.EMERGING_NARRATIVE
    elif isinstance(posts_pct, float) and posts_pct >= 0.15:
        trend = WorkspaceTrend.GROWING
    elif isinstance(posts_pct, float) and posts_pct <= -0.15:
        trend = WorkspaceTrend.DECLINING
    elif len(removed_entities) >= 5 and len(added_entities) >= 5:
        trend = WorkspaceTrend.FRAGMENTING
    else:
        trend = WorkspaceTrend.STABLE

    comparable = min(float(baseline.get("coverage_ratio", 0)), float(current.get("coverage_ratio", 0)))
    confidence = max(0.0, min(1.0, comparable * (0.75 + min(len(observations), 5) * 0.04)))
    observations.sort(key=lambda x: (-_SEVERITY.get(x.severity, 0), -x.confidence, x.category))

    return WorkspaceEvolutionReport(
        workspace_id=str(current.get("workspace_id") or baseline.get("workspace_id")),
        workspace_name=workspace_name,
        baseline_snapshot_id=baseline_snapshot_id,
        current_snapshot_id=current_snapshot_id,
        baseline_generated_at=datetime.fromisoformat(str(baseline["generated_at"])),
        current_generated_at=datetime.fromisoformat(str(current["generated_at"])),
        trend=trend,
        confidence=confidence,
        metric_deltas=metric_deltas,
        added_entities=added_entities,
        removed_entities=removed_entities,
        added_domains=added_domains,
        removed_domains=removed_domains,
        added_keywords=added_keywords,
        removed_keywords=removed_keywords,
        alert_delta=alert_delta,
        observations=tuple(observations),
        limitations=(
            "Сравниваются сохранённые snapshots; исходные публикации повторно не анализируются.",
            "Изменение частоты не доказывает причинность, влияние или координацию.",
            "Снижение покрытия уменьшает сопоставимость периодов.",
        ),
    )
