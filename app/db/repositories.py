from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AnalysisJobRecord, PostRecord
from app.domain.models import ChannelSnapshot, JobStatus
from app.profiles.models import IntelligenceProfile


@dataclass(slots=True, frozen=True)
class StoredProfileVersion:
    profile_id: str
    version: int
    profile: IntelligenceProfile


class JobRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(self, telegram_user_id: int, channel_username: str) -> str:
        async with self._session_factory() as session:
            record = AnalysisJobRecord(
                telegram_user_id=telegram_user_id,
                channel_username=channel_username,
                status=JobStatus.PENDING.value,
                progress_step=0,
                progress_text="Задание создано",
            )
            session.add(record)
            await session.commit()
            return record.id

    async def update_progress(
        self, job_id: str, status: JobStatus, step: int, text: str
    ) -> None:
        async with self._session_factory() as session:
            record = await session.get(AnalysisJobRecord, job_id)
            if record is None:
                raise LookupError(f"Задание {job_id} не найдено")
            record.status = status.value
            record.progress_step = step
            record.progress_text = text
            record.updated_at = datetime.now(UTC)
            await session.commit()

    async def save_result(
        self,
        job_id: str,
        snapshot: ChannelSnapshot,
        metrics: dict[str, object],
        report_path: str,
    ) -> None:
        async with self._session_factory() as session:
            record = await session.get(AnalysisJobRecord, job_id)
            if record is None:
                raise LookupError(f"Задание {job_id} не найдено")
            record.status = JobStatus.COMPLETED.value
            record.progress_step = 5
            record.progress_text = "Отчёт готов"
            record.metrics_json = metrics
            record.report_path = report_path
            record.updated_at = datetime.now(UTC)
            record.posts = [
                PostRecord(
                    message_id=post.message_id,
                    published_at=post.published_at,
                    text=post.text,
                    views=post.views,
                    reactions=post.reactions,
                    forwards=post.forwards,
                    url=post.url,
                )
                for post in snapshot.posts
            ]
            await session.commit()


    async def save_comparison_result(
        self, job_id: str, result: dict[str, object], report_path: str
    ) -> None:
        async with self._session_factory() as session:
            record = await session.get(AnalysisJobRecord, job_id)
            if record is None:
                raise LookupError(f"Задание {job_id} не найдено")
            record.status = JobStatus.COMPLETED.value
            record.progress_step = 5
            record.progress_text = "Сравнительный отчёт готов"
            record.metrics_json = result
            record.report_path = report_path
            record.updated_at = datetime.now(UTC)
            await session.commit()

    async def fail(self, job_id: str, error_message: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(AnalysisJobRecord, job_id)
            if record is None:
                return
            record.status = JobStatus.FAILED.value
            record.progress_text = "Ошибка"
            record.error_message = error_message[:2000]
            record.updated_at = datetime.now(UTC)
            await session.commit()

    async def latest_for_user(self, telegram_user_id: int) -> AnalysisJobRecord | None:
        async with self._session_factory() as session:
            query = (
                select(AnalysisJobRecord)
                .where(AnalysisJobRecord.telegram_user_id == telegram_user_id)
                .order_by(desc(AnalysisJobRecord.created_at))
                .limit(1)
            )
            return (await session.execute(query)).scalar_one_or_none()


class ProfileRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_version(self, profile) -> tuple[str, int]:
        from app.db.models import ChannelProfileRecord, ChannelProfileVersionRecord

        async with self._session_factory() as session:
            query = select(ChannelProfileRecord).where(ChannelProfileRecord.username == profile.username)
            record = (await session.execute(query)).scalar_one_or_none()
            if record is None:
                record = ChannelProfileRecord(username=profile.username, title=profile.title, subscribers=profile.subscribers)
                session.add(record)
                await session.flush()
            record.title = profile.title
            record.subscribers = profile.subscribers
            record.latest_version += 1
            record.updated_at = datetime.now(UTC)
            version = ChannelProfileVersionRecord(
                profile_id=record.id,
                version=record.latest_version,
                collected_at=profile.collected_at,
                source_post_count=profile.source_post_count,
                methodology_version=profile.methodology_version,
                confidence=profile.confidence,
                metrics_json=profile.metrics,
                content_dna_json=profile.content_dna,
                component_vectors_json={
                    "style": list(profile.style_vector),
                    "temporal": list(profile.temporal_vector),
                    "structural": list(profile.structural_vector),
                    "narrative": list(profile.narrative_vector),
                },
                embedding=list(profile.combined_vector),
            )
            session.add(version)
            await session.commit()
            return record.id, record.latest_version

    @staticmethod
    def _to_stored(profile_record, version_record) -> StoredProfileVersion:
        components = version_record.component_vectors_json
        profile = IntelligenceProfile(
            username=profile_record.username,
            title=profile_record.title,
            subscribers=profile_record.subscribers,
            collected_at=version_record.collected_at,
            source_post_count=version_record.source_post_count,
            methodology_version=version_record.methodology_version,
            style_vector=tuple(float(v) for v in components.get("style", [])),
            temporal_vector=tuple(float(v) for v in components.get("temporal", [])),
            structural_vector=tuple(float(v) for v in components.get("structural", [])),
            narrative_vector=tuple(float(v) for v in components.get("narrative", [])),
            combined_vector=tuple(float(v) for v in version_record.embedding),
            metrics=version_record.metrics_json,
            content_dna=version_record.content_dna_json,
            confidence=version_record.confidence,
        )
        return StoredProfileVersion(profile_record.id, version_record.version, profile)

    async def get_latest(self, username: str) -> StoredProfileVersion | None:
        from app.db.models import ChannelProfileRecord, ChannelProfileVersionRecord

        query = (
            select(ChannelProfileRecord, ChannelProfileVersionRecord)
            .join(ChannelProfileVersionRecord, ChannelProfileVersionRecord.profile_id == ChannelProfileRecord.id)
            .where(ChannelProfileRecord.username == username.lower().lstrip("@"))
            .where(ChannelProfileVersionRecord.version == ChannelProfileRecord.latest_version)
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).first()
            return self._to_stored(*row) if row else None

    async def get_version(self, username: str, version: int) -> StoredProfileVersion | None:
        from app.db.models import ChannelProfileRecord, ChannelProfileVersionRecord

        query = (
            select(ChannelProfileRecord, ChannelProfileVersionRecord)
            .join(ChannelProfileVersionRecord, ChannelProfileVersionRecord.profile_id == ChannelProfileRecord.id)
            .where(ChannelProfileRecord.username == username.lower().lstrip("@"))
            .where(ChannelProfileVersionRecord.version == version)
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).first()
            return self._to_stored(*row) if row else None

    async def nearest(self, embedding: list[float] | tuple[float, ...], limit: int = 10, exclude_username: str | None = None):
        from app.db.models import ChannelProfileRecord, ChannelProfileVersionRecord

        distance = ChannelProfileVersionRecord.embedding.cosine_distance(list(embedding)).label("distance")
        query = (
            select(ChannelProfileRecord.username, ChannelProfileVersionRecord.version, distance)
            .join(ChannelProfileVersionRecord, ChannelProfileVersionRecord.profile_id == ChannelProfileRecord.id)
            .where(ChannelProfileVersionRecord.version == ChannelProfileRecord.latest_version)
            .order_by(distance)
            .limit(limit)
        )
        if exclude_username:
            query = query.where(ChannelProfileRecord.username != exclude_username)
        async with self._session_factory() as session:
            rows = (await session.execute(query)).all()
            return [(username, version, max(0.0, 1.0 - float(dist))) for username, version, dist in rows]


class EvolutionRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_report(self, profile_id: str, report) -> int:
        import hashlib
        import json
        from app.db.models import ProfileChangeRecord

        saved = 0
        async with self._session_factory() as session:
            for event in report.events:
                raw = json.dumps({
                    "type": event.event_type,
                    "category": event.category,
                    "title": event.title,
                    "old": event.old_value,
                    "new": event.new_value,
                }, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                fingerprint = hashlib.sha256(raw).hexdigest()
                query = select(ProfileChangeRecord).where(
                    ProfileChangeRecord.profile_id == profile_id,
                    ProfileChangeRecord.from_version == report.from_version,
                    ProfileChangeRecord.to_version == report.to_version,
                    ProfileChangeRecord.event_fingerprint == fingerprint,
                )
                if (await session.execute(query)).scalar_one_or_none() is not None:
                    continue
                session.add(ProfileChangeRecord(
                    profile_id=profile_id,
                    channel_username=report.username,
                    from_version=report.from_version,
                    to_version=report.to_version,
                    event_type=event.event_type,
                    category=event.category,
                    severity=event.severity.value,
                    title=event.title,
                    description=event.description,
                    confidence=event.confidence,
                    old_value_json=event.old_value,
                    new_value_json=event.new_value,
                    delta=event.delta,
                    evidence_message_ids=list(event.evidence),
                    event_fingerprint=fingerprint,
                ))
                saved += 1
            await session.commit()
        return saved

    async def latest_changes(self, username: str, limit: int = 20):
        from app.db.models import ProfileChangeRecord
        query = (
            select(ProfileChangeRecord)
            .where(ProfileChangeRecord.channel_username == username.lower().lstrip("@"))
            .order_by(desc(ProfileChangeRecord.to_version), desc(ProfileChangeRecord.created_at))
            .limit(max(1, min(limit, 100)))
        )
        async with self._session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    async def history(self, username: str):
        from app.db.models import ChannelProfileRecord, ChannelProfileVersionRecord
        query = (
            select(ChannelProfileVersionRecord)
            .join(ChannelProfileRecord, ChannelProfileVersionRecord.profile_id == ChannelProfileRecord.id)
            .where(ChannelProfileRecord.username == username.lower().lstrip("@"))
            .order_by(desc(ChannelProfileVersionRecord.version))
        )
        async with self._session_factory() as session:
            return list((await session.execute(query)).scalars().all())


class GraphRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_snapshot(self, graph, profile_id: str) -> str:
        from app.db.models import (
            EntityAliasRecord,
            EntityMentionRecord,
            EntityRecord,
            GraphSnapshotRecord,
            RelationshipRecord,
        )

        async with self._session_factory() as session:
            existing_query = select(GraphSnapshotRecord).where(
                GraphSnapshotRecord.profile_id == profile_id,
                GraphSnapshotRecord.profile_version == graph.profile_version,
            )
            existing = (await session.execute(existing_query)).scalar_one_or_none()
            if existing is not None:
                return existing.id

            entity_records: dict[tuple[str, str], EntityRecord] = {}
            for entity in graph.entities:
                query = select(EntityRecord).where(
                    EntityRecord.entity_type == entity.entity_type.value,
                    EntityRecord.canonical_name == entity.canonical_name,
                )
                record = (await session.execute(query)).scalar_one_or_none()
                if record is None:
                    record = EntityRecord(
                        entity_type=entity.entity_type.value,
                        canonical_name=entity.canonical_name,
                        display_name=entity.display_name,
                        confidence=entity.confidence,
                    )
                    session.add(record)
                    await session.flush()
                else:
                    record.display_name = entity.display_name
                    record.confidence = max(record.confidence, entity.confidence)
                entity_records[entity.key] = record
                for alias in entity.aliases:
                    alias_query = select(EntityAliasRecord).where(
                        EntityAliasRecord.entity_id == record.id,
                        EntityAliasRecord.alias == alias.casefold(),
                    )
                    if (await session.execute(alias_query)).scalar_one_or_none() is None:
                        session.add(EntityAliasRecord(entity_id=record.id, alias=alias.casefold()))

            snapshot_record = GraphSnapshotRecord(
                profile_id=profile_id,
                profile_version=graph.profile_version,
                collected_at=graph.collected_at,
                entity_count=len(graph.entities),
                relationship_count=len(graph.relationships),
            )
            session.add(snapshot_record)
            await session.flush()

            for mention in graph.mentions:
                entity_record = entity_records[mention.entity.key]
                session.add(
                    EntityMentionRecord(
                        graph_snapshot_id=snapshot_record.id,
                        entity_id=entity_record.id,
                        channel_username=graph.channel_username,
                        message_id=mention.message_id,
                        published_at=mention.published_at,
                        mention_count=mention.count,
                        evidence_text=mention.evidence_text,
                        confidence=mention.entity.confidence,
                    )
                )

            for relationship in graph.relationships:
                target = entity_records[relationship.target.key]
                session.add(
                    RelationshipRecord(
                        graph_snapshot_id=snapshot_record.id,
                        source_type=relationship.source_type,
                        source_name=relationship.source_name,
                        target_entity_id=target.id,
                        relation_type=relationship.relation_type.value,
                        weight=relationship.weight,
                        confidence=relationship.confidence,
                        evidence_message_ids=list(relationship.evidence_message_ids),
                    )
                )
            await session.commit()
            return snapshot_record.id

    async def entity_summary(self, query_text: str, entity_type: str | None = None):
        from sqlalchemy import func, or_
        from app.db.models import EntityAliasRecord, EntityMentionRecord, EntityRecord
        from app.graph.queries import EntityChannelStat, EntitySummary

        normalized = query_text.strip().casefold().lstrip("@#")
        entity_query = (
            select(EntityRecord)
            .outerjoin(EntityAliasRecord, EntityAliasRecord.entity_id == EntityRecord.id)
            .where(
                or_(
                    EntityRecord.canonical_name == normalized,
                    func.lower(EntityRecord.display_name) == normalized,
                    EntityAliasRecord.alias == normalized,
                )
            )
            .limit(1)
        )
        if entity_type:
            entity_query = entity_query.where(EntityRecord.entity_type == entity_type)
        async with self._session_factory() as session:
            entity = (await session.execute(entity_query)).scalar_one_or_none()
            if entity is None:
                return None
            stats_query = (
                select(
                    EntityMentionRecord.channel_username,
                    func.sum(EntityMentionRecord.mention_count),
                    func.count(func.distinct(EntityMentionRecord.message_id)),
                    func.min(EntityMentionRecord.published_at),
                    func.max(EntityMentionRecord.published_at),
                )
                .where(EntityMentionRecord.entity_id == entity.id)
                .group_by(EntityMentionRecord.channel_username)
                .order_by(desc(func.sum(EntityMentionRecord.mention_count)))
            )
            rows = (await session.execute(stats_query)).all()
            channels = tuple(
                EntityChannelStat(username, int(mentions), int(posts), first_seen, last_seen)
                for username, mentions, posts, first_seen, last_seen in rows
            )
            return EntitySummary(
                entity_type=entity.entity_type,
                canonical_name=entity.canonical_name,
                display_name=entity.display_name,
                total_mentions=sum(item.mentions for item in channels),
                post_count=sum(item.posts for item in channels),
                channel_count=len(channels),
                channels=channels,
            )

    async def timeline(self, query_text: str, entity_type: str | None = None):
        from sqlalchemy import func, or_
        from app.db.models import EntityAliasRecord, EntityMentionRecord, EntityRecord
        from app.graph.queries import TimelineBucket

        normalized = query_text.strip().casefold().lstrip("@#")
        entity_query = (
            select(EntityRecord.id)
            .outerjoin(EntityAliasRecord, EntityAliasRecord.entity_id == EntityRecord.id)
            .where(
                or_(
                    EntityRecord.canonical_name == normalized,
                    func.lower(EntityRecord.display_name) == normalized,
                    EntityAliasRecord.alias == normalized,
                )
            )
            .limit(1)
        )
        if entity_type:
            entity_query = entity_query.where(EntityRecord.entity_type == entity_type)
        async with self._session_factory() as session:
            entity_id = (await session.execute(entity_query)).scalar_one_or_none()
            if entity_id is None:
                return tuple()
            period = func.to_char(EntityMentionRecord.published_at, "YYYY-MM").label("period")
            timeline_query = (
                select(
                    period,
                    func.sum(EntityMentionRecord.mention_count),
                    func.count(func.distinct(EntityMentionRecord.message_id)),
                )
                .where(EntityMentionRecord.entity_id == entity_id)
                .group_by(period)
                .order_by(period)
            )
            rows = (await session.execute(timeline_query)).all()
            return tuple(TimelineBucket(str(p), int(m), int(posts)) for p, m, posts in rows)


class MonitoringRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def add_watch(self, telegram_user_id: int, chat_id: int, username: str, sensitivity: str = "high", interval_minutes: int = 360):
        from app.db.models import WatchlistRecord
        username = username.lower().lstrip("@")
        sensitivity = sensitivity.casefold()
        if sensitivity not in {"low", "medium", "high", "critical"}:
            raise ValueError("Чувствительность: low, medium, high или critical")
        interval_minutes = max(60, min(int(interval_minutes), 10080))
        async with self._session_factory() as session:
            query = select(WatchlistRecord).where(
                WatchlistRecord.telegram_user_id == telegram_user_id,
                WatchlistRecord.channel_username == username,
            )
            record = (await session.execute(query)).scalar_one_or_none()
            now = datetime.now(UTC)
            if record is None:
                record = WatchlistRecord(
                    telegram_user_id=telegram_user_id,
                    chat_id=chat_id,
                    channel_username=username,
                    sensitivity=sensitivity,
                    interval_minutes=interval_minutes,
                    next_check_at=now,
                )
                session.add(record)
            else:
                record.chat_id = chat_id
                record.sensitivity = sensitivity
                record.interval_minutes = interval_minutes
                record.enabled = True
                record.next_check_at = min(record.next_check_at, now)
                record.updated_at = now
            await session.commit()
            await session.refresh(record)
            return record

    async def remove_watch(self, telegram_user_id: int, username: str) -> bool:
        from app.db.models import WatchlistRecord
        query = select(WatchlistRecord).where(
            WatchlistRecord.telegram_user_id == telegram_user_id,
            WatchlistRecord.channel_username == username.lower().lstrip("@"),
        )
        async with self._session_factory() as session:
            record = (await session.execute(query)).scalar_one_or_none()
            if record is None:
                return False
            await session.delete(record)
            await session.commit()
            return True

    async def list_watches(self, telegram_user_id: int):
        from app.db.models import WatchlistRecord
        query = (
            select(WatchlistRecord)
            .where(WatchlistRecord.telegram_user_id == telegram_user_id)
            .order_by(WatchlistRecord.channel_username)
        )
        async with self._session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    async def due(self, now: datetime, limit: int = 25):
        from app.db.models import WatchlistRecord
        query = (
            select(WatchlistRecord)
            .where(WatchlistRecord.enabled.is_(True), WatchlistRecord.next_check_at <= now)
            .order_by(WatchlistRecord.next_check_at)
            .limit(max(1, min(limit, 100)))
        )
        async with self._session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    async def mark_checked(self, watch_id: str, profile_version: int | None, error: str | None) -> None:
        from app.db.models import WatchlistRecord
        async with self._session_factory() as session:
            record = await session.get(WatchlistRecord, watch_id)
            if record is None:
                return
            now = datetime.now(UTC)
            record.last_checked_at = now
            record.next_check_at = now + timedelta(minutes=record.interval_minutes)
            record.last_profile_version = profile_version
            record.last_error = error[:2000] if error else None
            record.consecutive_failures = record.consecutive_failures + 1 if error else 0
            if record.consecutive_failures >= 10:
                record.enabled = False
            record.updated_at = now
            await session.commit()

    async def save_alerts(self, watch, profile_version: int, alerts):
        from app.db.models import AlertEventRecord
        saved = []
        async with self._session_factory() as session:
            for alert in alerts:
                query = select(AlertEventRecord).where(
                    AlertEventRecord.watchlist_id == watch.id,
                    AlertEventRecord.event_fingerprint == alert.fingerprint,
                )
                if (await session.execute(query)).scalar_one_or_none() is not None:
                    continue
                session.add(AlertEventRecord(
                    watchlist_id=watch.id,
                    telegram_user_id=watch.telegram_user_id,
                    channel_username=watch.channel_username,
                    profile_version=profile_version,
                    severity=alert.severity.value,
                    category=alert.category,
                    title=alert.title,
                    description=alert.description,
                    confidence=alert.confidence,
                    evidence_message_ids=list(alert.evidence),
                    event_fingerprint=alert.fingerprint,
                ))
                saved.append(alert)
            await session.commit()
        return tuple(saved)

    async def recent_alerts(self, telegram_user_id: int, hours: int = 24, limit: int = 50):
        from app.db.models import AlertEventRecord
        since = datetime.now(UTC) - timedelta(hours=max(1, min(hours, 24 * 31)))
        query = (
            select(AlertEventRecord)
            .where(AlertEventRecord.telegram_user_id == telegram_user_id, AlertEventRecord.created_at >= since)
            .order_by(desc(AlertEventRecord.created_at))
            .limit(max(1, min(limit, 200)))
        )
        async with self._session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    async def digest(self, telegram_user_id: int, hours: int = 24):
        from app.db.models import AlertEventRecord, WatchlistRecord
        since = datetime.now(UTC) - timedelta(hours=hours)
        async with self._session_factory() as session:
            watched = (await session.execute(
                select(func.count()).select_from(WatchlistRecord).where(
                    WatchlistRecord.telegram_user_id == telegram_user_id,
                    WatchlistRecord.enabled.is_(True),
                )
            )).scalar_one()
            rows = (await session.execute(
                select(AlertEventRecord.severity, func.count())
                .where(AlertEventRecord.telegram_user_id == telegram_user_id, AlertEventRecord.created_at >= since)
                .group_by(AlertEventRecord.severity)
            )).all()
            return int(watched), {severity: int(count) for severity, count in rows}

    async def mark_delivered(self, fingerprint: str, watch_id: str, chat_id: int, message_id: int) -> None:
        from app.db.models import AlertDeliveryRecord, AlertEventRecord
        async with self._session_factory() as session:
            query = select(AlertEventRecord).where(
                AlertEventRecord.watchlist_id == watch_id,
                AlertEventRecord.event_fingerprint == fingerprint,
            )
            alert = (await session.execute(query)).scalar_one_or_none()
            if alert is None:
                return
            alert.delivered_at = datetime.now(UTC)
            session.add(AlertDeliveryRecord(
                alert_event_id=alert.id,
                chat_id=chat_id,
                status="delivered",
                telegram_message_id=message_id,
            ))
            await session.commit()

    async def mark_delivery_failed(self, fingerprint: str, watch_id: str, chat_id: int, error: str) -> None:
        from app.db.models import AlertDeliveryRecord, AlertEventRecord
        async with self._session_factory() as session:
            query = select(AlertEventRecord).where(
                AlertEventRecord.watchlist_id == watch_id,
                AlertEventRecord.event_fingerprint == fingerprint,
            )
            alert = (await session.execute(query)).scalar_one_or_none()
            if alert is None:
                return
            session.add(AlertDeliveryRecord(
                alert_event_id=alert.id,
                chat_id=chat_id,
                status="failed",
                error_message=error[:2000],
            ))
            await session.commit()
