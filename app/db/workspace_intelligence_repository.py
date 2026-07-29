from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import (
    AlertEventRecord,
    ChannelProfileRecord,
    ChannelProfileVersionRecord,
    EntityMentionRecord,
    EntityRecord,
    WorkspaceIntelligenceSnapshotRecord,
)
from app.workspace_intelligence.models import (
    ChannelIntelligence,
    WorkspaceAlertFact,
    WorkspaceIntelligenceInput,
    WorkspaceIntelligenceReport,
)
from app.workspaces.models import Workspace, WorkspaceItemType


class WorkspaceIntelligenceRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _metric(metrics: dict, *names: str) -> float | None:
        for name in names:
            value = metrics.get(name)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    async def build_input(self, workspace: Workspace, lookback_days: int = 30) -> WorkspaceIntelligenceInput:
        channels = tuple(
            item.normalized_value for item in workspace.items if item.item_type is WorkspaceItemType.CHANNEL
        )
        entities = tuple(
            item.normalized_value for item in workspace.items if item.item_type is WorkspaceItemType.ENTITY
        )
        domains = tuple(
            item.normalized_value for item in workspace.items if item.item_type is WorkspaceItemType.DOMAIN
        )
        keywords = tuple(
            item.normalized_value for item in workspace.items if item.item_type is WorkspaceItemType.KEYWORD
        )
        cutoff = datetime.now(UTC) - timedelta(days=max(1, min(lookback_days, 3650)))

        async with self._session_factory() as session:
            profile_rows = []
            if channels:
                query = (
                    select(ChannelProfileRecord, ChannelProfileVersionRecord)
                    .join(
                        ChannelProfileVersionRecord,
                        (ChannelProfileVersionRecord.profile_id == ChannelProfileRecord.id)
                        & (ChannelProfileVersionRecord.version == ChannelProfileRecord.latest_version),
                    )
                    .where(ChannelProfileRecord.username.in_(channels))
                )
                profile_rows = list((await session.execute(query)).all())

            channel_facts: list[ChannelIntelligence] = []
            for profile, version in profile_rows:
                metrics = version.metrics_json or {}
                advanced = metrics.get("advanced") if isinstance(metrics.get("advanced"), dict) else {}
                semantic = advanced.get("semantic") if isinstance(advanced.get("semantic"), dict) else {}
                top_terms_raw = semantic.get("top_terms", []) if isinstance(semantic, dict) else []
                top_terms: list[str] = []
                for item in top_terms_raw[:12]:
                    if isinstance(item, str):
                        top_terms.append(item)
                    elif isinstance(item, (list, tuple)) and item:
                        top_terms.append(str(item[0]))
                    elif isinstance(item, dict) and item.get("term"):
                        top_terms.append(str(item["term"]))

                entity_count_query = (
                    select(func.count(func.distinct(EntityMentionRecord.entity_id)))
                    .where(EntityMentionRecord.channel_username == profile.username)
                )
                entity_count = int((await session.execute(entity_count_query)).scalar_one() or 0)
                domain_count_query = (
                    select(func.count(func.distinct(EntityMentionRecord.entity_id)))
                    .join(EntityRecord, EntityRecord.id == EntityMentionRecord.entity_id)
                    .where(
                        EntityMentionRecord.channel_username == profile.username,
                        EntityRecord.entity_type == "domain",
                    )
                )
                domain_count = int((await session.execute(domain_count_query)).scalar_one() or 0)
                channel_facts.append(ChannelIntelligence(
                    username=profile.username,
                    profile_version=version.version,
                    posts_count=version.source_post_count,
                    confidence=version.confidence,
                    mean_views=self._metric(metrics, "mean_views"),
                    engagement_per_1000=self._metric(metrics, "engagement_per_1000_views", "engagement_per_1000"),
                    posts_per_day=self._metric(metrics, "posts_per_day"),
                    top_terms=tuple(top_terms),
                    entities_count=entity_count,
                    domains_count=domain_count,
                    latest_collected_at=version.collected_at,
                ))

            entity_mentions: dict[str, int] = {}
            if entities:
                query = (
                    select(EntityRecord.display_name, func.sum(EntityMentionRecord.mention_count))
                    .join(EntityMentionRecord, EntityMentionRecord.entity_id == EntityRecord.id)
                    .where(
                        func.lower(EntityRecord.display_name).in_([item.casefold() for item in entities]),
                        EntityMentionRecord.published_at >= cutoff,
                    )
                    .group_by(EntityRecord.display_name)
                )
                entity_mentions = {name: int(count or 0) for name, count in (await session.execute(query)).all()}

            domain_mentions: dict[str, int] = {}
            if domains:
                query = (
                    select(EntityRecord.display_name, func.sum(EntityMentionRecord.mention_count))
                    .join(EntityMentionRecord, EntityMentionRecord.entity_id == EntityRecord.id)
                    .where(
                        EntityRecord.entity_type == "domain",
                        EntityRecord.canonical_name.in_(domains),
                        EntityMentionRecord.published_at >= cutoff,
                    )
                    .group_by(EntityRecord.display_name)
                )
                domain_mentions = {name: int(count or 0) for name, count in (await session.execute(query)).all()}

            keyword_mentions = {keyword: 0 for keyword in keywords}
            for channel in channel_facts:
                terms = {term.casefold() for term in channel.top_terms}
                for keyword in keywords:
                    if keyword.casefold() in terms:
                        keyword_mentions[keyword] += 1

            alert_facts: list[WorkspaceAlertFact] = []
            if channels:
                query = (
                    select(AlertEventRecord)
                    .where(
                        AlertEventRecord.telegram_user_id == workspace.telegram_user_id,
                        AlertEventRecord.channel_username.in_(channels),
                        AlertEventRecord.created_at >= cutoff,
                    )
                    .order_by(desc(AlertEventRecord.created_at))
                    .limit(200)
                )
                for record in (await session.execute(query)).scalars().all():
                    alert_facts.append(WorkspaceAlertFact(
                        record.channel_username,
                        record.severity,
                        record.title,
                        record.confidence,
                        record.created_at,
                    ))

        return WorkspaceIntelligenceInput(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            requested_channels=channels,
            channels=tuple(channel_facts),
            entity_mentions=entity_mentions,
            domain_mentions=domain_mentions,
            keyword_mentions=keyword_mentions,
            alerts=tuple(alert_facts),
            generated_at=datetime.now(UTC),
        )

    async def save_snapshot(self, report: WorkspaceIntelligenceReport, report_path: str | None = None) -> str:
        async with self._session_factory() as session:
            record = WorkspaceIntelligenceSnapshotRecord(
                workspace_id=report.workspace_id,
                generated_at=report.generated_at,
                methodology_version=report.methodology_version,
                coverage_status=report.coverage_status.value,
                coverage_ratio=report.coverage_ratio,
                analyzed_channel_count=report.analyzed_channel_count,
                total_posts=report.total_posts,
                confidence=report.weighted_confidence,
                report_json=report.to_dict(),
                report_path=report_path,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id

    async def latest_snapshot(self, workspace_id: str):
        query = (
            select(WorkspaceIntelligenceSnapshotRecord)
            .where(WorkspaceIntelligenceSnapshotRecord.workspace_id == workspace_id)
            .order_by(desc(WorkspaceIntelligenceSnapshotRecord.generated_at))
            .limit(1)
        )
        async with self._session_factory() as session:
            return (await session.execute(query)).scalar_one_or_none()
