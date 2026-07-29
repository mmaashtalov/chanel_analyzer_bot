from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from statistics import fmean

from app.workspace_intelligence.models import (
    CoverageStatus,
    WorkspaceFinding,
    WorkspaceIntelligenceInput,
    WorkspaceIntelligenceReport,
)

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _weighted_average(values: list[tuple[float, int]]) -> float | None:
    denominator = sum(weight for _, weight in values)
    if denominator <= 0:
        return None
    return sum(value * weight for value, weight in values) / denominator


def _top(values: dict[str, int], limit: int = 12) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(values.items(), key=lambda item: (-item[1], item[0].casefold()))[:limit])


def build_workspace_intelligence(data: WorkspaceIntelligenceInput) -> WorkspaceIntelligenceReport:
    generated_at = data.generated_at or datetime.now(UTC)
    requested = len(set(data.requested_channels))
    analyzed = len({channel.username for channel in data.channels})
    coverage_ratio = analyzed / requested if requested else (1.0 if data.channels else 0.0)
    if analyzed == 0:
        coverage = CoverageStatus.EMPTY
    elif coverage_ratio >= 0.999:
        coverage = CoverageStatus.COMPLETE
    else:
        coverage = CoverageStatus.PARTIAL

    total_posts = sum(max(0, channel.posts_count) for channel in data.channels)
    confidence = _weighted_average(
        [(max(0.0, min(1.0, channel.confidence)), max(1, channel.posts_count)) for channel in data.channels]
    ) or 0.0
    mean_views = _weighted_average([
        (channel.mean_views, max(1, channel.posts_count))
        for channel in data.channels if channel.mean_views is not None
    ])
    mean_engagement = _weighted_average([
        (channel.engagement_per_1000, max(1, channel.posts_count))
        for channel in data.channels if channel.engagement_per_1000 is not None
    ])
    mean_activity = fmean([
        channel.posts_per_day for channel in data.channels if channel.posts_per_day is not None
    ]) if any(channel.posts_per_day is not None for channel in data.channels) else None

    alert_counts = Counter(alert.severity.casefold() for alert in data.alerts)
    findings: list[WorkspaceFinding] = []

    if coverage is CoverageStatus.PARTIAL:
        missing = sorted(set(data.requested_channels) - {channel.username for channel in data.channels})
        findings.append(WorkspaceFinding(
            "coverage", "medium", "Неполное покрытие Workspace",
            f"Профили доступны для {analyzed} из {requested} каналов.",
            1.0, tuple(f"@{name}" for name in missing[:20]),
        ))
    elif coverage is CoverageStatus.EMPTY:
        findings.append(WorkspaceFinding(
            "coverage", "high", "Нет аналитических профилей",
            "Сначала выполните /analyze для каналов, добавленных в Workspace.", 1.0,
        ))

    if data.alerts:
        important = [a for a in data.alerts if _SEVERITY_ORDER.get(a.severity.casefold(), 0) >= 3]
        if important:
            top_alert = max(important, key=lambda a: (_SEVERITY_ORDER.get(a.severity.casefold(), 0), a.confidence))
            findings.append(WorkspaceFinding(
                "alerts", top_alert.severity.casefold(), "Зафиксированы важные изменения",
                f"High/Critical событий: {len(important)}. Последний приоритетный сигнал: {top_alert.title}",
                top_alert.confidence, tuple(f"@{a.channel_username}: {a.title}" for a in important[:10]),
            ))

    top_entities = _top(data.entity_mentions)
    if top_entities:
        name, count = top_entities[0]
        findings.append(WorkspaceFinding(
            "entities", "medium", "Доминирующая сущность",
            f"Сущность «{name}» имеет наибольшую частоту в контуре Workspace: {count} упоминаний.",
            min(0.95, 0.55 + min(count, 40) / 100), (name,),
        ))

    top_domains = _top(data.domain_mentions)
    if top_domains:
        name, count = top_domains[0]
        findings.append(WorkspaceFinding(
            "sources", "low", "Наиболее используемый домен",
            f"Домен {name} лидирует среди выявленных внешних источников: {count} упоминаний.",
            min(0.95, 0.6 + min(count, 35) / 100), (name,),
        ))

    active_channels = sorted(
        (channel for channel in data.channels if channel.posts_per_day is not None),
        key=lambda channel: channel.posts_per_day or 0,
        reverse=True,
    )
    if active_channels:
        leader = active_channels[0]
        findings.append(WorkspaceFinding(
            "activity", "low", "Лидер публикационной активности",
            f"@{leader.username}: {leader.posts_per_day:.1f} публикаций в сутки.",
            leader.confidence, (f"@{leader.username}",),
        ))

    findings.sort(key=lambda item: (-_SEVERITY_ORDER.get(item.severity, 0), -item.confidence, item.title))
    limitations: list[str] = [
        "Отчёт агрегирует только данные, уже сохранённые в платформе.",
        "Отсутствие профиля не означает отсутствие активности канала.",
        "Частота упоминаний не доказывает связь, влияние или координацию.",
    ]
    if requested == 0:
        limitations.append("В Workspace не добавлены Telegram-каналы; количественная часть ограничена.")

    return WorkspaceIntelligenceReport(
        workspace_id=data.workspace_id,
        workspace_name=data.workspace_name,
        generated_at=generated_at,
        coverage_status=coverage,
        coverage_ratio=coverage_ratio,
        requested_channel_count=requested,
        analyzed_channel_count=analyzed,
        total_posts=total_posts,
        weighted_confidence=confidence,
        mean_views=mean_views,
        mean_engagement_per_1000=mean_engagement,
        mean_posts_per_day=mean_activity,
        top_entities=top_entities,
        top_domains=top_domains,
        top_keywords=_top(data.keyword_mentions),
        alert_counts=dict(alert_counts),
        channels=tuple(sorted(data.channels, key=lambda item: item.username)),
        findings=tuple(findings),
        limitations=tuple(limitations),
    )
