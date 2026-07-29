import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # local test environment without optional DB extension package
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):
        cache_ok = True

        def __init__(self, dimensions: int) -> None:
            self.dimensions = dimensions

        def get_col_spec(self, **kw) -> str:
            return f"VECTOR({self.dimensions})"


from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class AnalysisJobRecord(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    channel_username: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False, default="quantitative")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    progress_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_text: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    report_path: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    posts: Mapped[list["PostRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class PostRecord(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("job_id", "message_id", name="uq_posts_job_message"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    views: Mapped[int | None] = mapped_column(BigInteger)
    reactions: Mapped[int | None] = mapped_column(Integer)
    forwards: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(Text)
    job: Mapped[AnalysisJobRecord] = relationship(back_populates="posts")


class ChannelProfileRecord(Base):
    __tablename__ = "channel_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subscribers: Mapped[int | None] = mapped_column(BigInteger)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    versions: Mapped[list["ChannelProfileVersionRecord"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class ChannelProfileVersionRecord(Base):
    __tablename__ = "channel_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version", name="uq_profile_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(ForeignKey("channel_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_post_count: Mapped[int] = mapped_column(Integer, nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_dna_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    component_vectors_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    profile: Mapped[ChannelProfileRecord] = relationship(back_populates="versions")


class EntityRecord(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("entity_type", "canonical_name", name="uq_entity_type_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class EntityAliasRecord(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "alias", name="uq_entity_alias"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    alias: Mapped[str] = mapped_column(String(512), index=True, nullable=False)


class GraphSnapshotRecord(Base):
    __tablename__ = "graph_snapshots"
    __table_args__ = (UniqueConstraint("profile_id", "profile_version", name="uq_graph_profile_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(ForeignKey("channel_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EntityMentionRecord(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        UniqueConstraint("graph_snapshot_id", "entity_id", "message_id", name="uq_graph_entity_message"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    graph_snapshot_id: Mapped[str] = mapped_column(ForeignKey("graph_snapshots.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    channel_username: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class RelationshipRecord(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("graph_snapshot_id", "target_entity_id", "relation_type", name="uq_graph_target_relation"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    graph_snapshot_id: Mapped[str] = mapped_column(ForeignKey("graph_snapshots.id", ondelete="CASCADE"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_message_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)


class ProfileChangeRecord(Base):
    __tablename__ = "profile_changes"
    __table_args__ = (
        UniqueConstraint("profile_id", "from_version", "to_version", "event_fingerprint", name="uq_profile_change_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(ForeignKey("channel_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    channel_username: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    old_value_json: Mapped[object | None] = mapped_column(JSON)
    new_value_json: Mapped[object | None] = mapped_column(JSON)
    delta: Mapped[float | None] = mapped_column(Float)
    evidence_message_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)


class WatchlistRecord(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("telegram_user_id", "channel_username", name="uq_watch_user_channel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    channel_username: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="high")
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=360)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, default=utcnow)
    last_profile_version: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AlertEventRecord(Base):
    __tablename__ = "alert_events"
    __table_args__ = (UniqueConstraint("watchlist_id", "event_fingerprint", name="uq_watch_alert_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    watchlist_id: Mapped[str] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    channel_username: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_message_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)


class AlertDeliveryRecord(Base):
    __tablename__ = "alert_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_event_id: Mapped[str] = mapped_column(ForeignKey("alert_events.id", ondelete="CASCADE"), index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SourceRecord(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("source_type", "external_id", name="uq_source_type_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    external_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512))
    adapter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SourceRunRecord(Base):
    __tablename__ = "source_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    collected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceDocumentRecord(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("source_id", "external_document_id", name="uq_source_external_document"),
        UniqueConstraint("fingerprint", name="uq_source_document_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"), index=True)
    external_document_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(512))
    language: Mapped[str | None] = mapped_column(String(16), index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SourceErrorRecord(Base):
    __tablename__ = "source_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"), index=True)
    error_type: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)


class WorkspaceRecord(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("telegram_user_id", "name_key", name="uq_workspace_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_key: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    items: Mapped[list["WorkspaceItemRecord"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceItemRecord(Base):
    __tablename__ = "workspace_items"
    __table_args__ = (UniqueConstraint("workspace_id", "item_type", "normalized_value", name="uq_workspace_item"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(1024), index=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    workspace: Mapped[WorkspaceRecord] = relationship(back_populates="items")


class WorkspaceIntelligenceSnapshotRecord(Base):
    __tablename__ = "workspace_intelligence_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    coverage_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    analyzed_channel_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_posts: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    report_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WorkspaceEvolutionReportRecord(Base):
    __tablename__ = "workspace_evolution_reports"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "baseline_snapshot_id", "current_snapshot_id",
            name="uq_workspace_evolution_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    baseline_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_intelligence_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    current_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_intelligence_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    baseline_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trend: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    report_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProvenanceBundleRecord(Base):
    __tablename__ = "provenance_bundles"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    completeness: Mapped[float] = mapped_column(Float, nullable=False)
    review_completeness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    integrity_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    bundle_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WorkspaceProvenanceLinkRecord(Base):
    __tablename__ = "workspace_provenance_links"
    __table_args__ = (
        UniqueConstraint("workspace_id", "bundle_id", name="uq_workspace_provenance_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    bundle_id: Mapped[str] = mapped_column(
        ForeignKey("provenance_bundles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="channel_analysis")
    source_item: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalyticClaimRecord(Base):
    __tablename__ = "analytic_claims"
    __table_args__ = (UniqueConstraint("bundle_id", "claim_index", name="uq_claim_bundle_index"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(
        ForeignKey("provenance_bundles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    assessment: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_quality: Mapped[float] = mapped_column(Float, nullable=False)
    caveats_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="unreviewed")
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    independence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    corroboration_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    corroboration_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    claim_identity_id: Mapped[str | None] = mapped_column(String(40), index=True)
    temporal_status: Mapped[str] = mapped_column(String(24), index=True, nullable=False, default="current")


class EvidenceReferenceRecord(Base):
    __tablename__ = "evidence_references"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(
        ForeignKey("provenance_bundles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    locator: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    strength: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value_json: Mapped[object | None] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("source_documents.id", ondelete="SET NULL"), index=True)
    source_type: Mapped[str | None] = mapped_column(String(32), index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(512))
    excerpt: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)


class ClaimEvidenceLinkRecord(Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_link"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_references.id", ondelete="CASCADE"), index=True, nullable=False
    )


class ClaimReviewEventRecord(Base):
    __tablename__ = "claim_review_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    bundle_id: Mapped[str] = mapped_column(
        ForeignKey("provenance_bundles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EvidenceRequestRecord(Base):
    __tablename__ = "evidence_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    claim_id: Mapped[str] = mapped_column(ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="queued")
    priority: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="normal")
    gap_codes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    query_terms_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_plan_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    documents_collected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_linked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    collection_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class EvidenceRequestEventRecord(Base):
    __tablename__ = "evidence_request_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id: Mapped[str] = mapped_column(ForeignKey("evidence_requests.id", ondelete="CASCADE"), index=True, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClaimIdentityRecord(Base):
    __tablename__ = "claim_identities"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    canonical_statement: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="SET NULL"), index=True
    )
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ClaimTimelineLinkRecord(Base):
    __tablename__ = "claim_timeline_links"
    __table_args__ = (UniqueConstraint("source_claim_id", "target_claim_id", "relation_type", name="uq_claim_timeline_relation"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    claim_identity_id: Mapped[str] = mapped_column(ForeignKey("claim_identities.id", ondelete="CASCADE"), index=True, nullable=False)
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False)
    target_claim_id: Mapped[str] = mapped_column(ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClaimContradictionRecord(Base):
    """Mutable queue projection for a detected contradiction.

    The audit trail is stored separately in ``ClaimContradictionEventRecord``;
    this row is only the current state used by triage queries.
    """

    __tablename__ = "claim_contradictions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "source_claim_id", "target_claim_id",
            name="uq_claim_contradiction_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_identity_id: Mapped[str] = mapped_column(
        ForeignKey("claim_identities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_claim_id: Mapped[str] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_claim_id: Mapped[str] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="medium")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="open")
    resolution_action: Mapped[str | None] = mapped_column(String(32), index=True)
    selected_claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="SET NULL"), index=True
    )
    resolution_comment: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[int | None] = mapped_column(BigInteger, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ClaimContradictionEventRecord(Base):
    """Append-only analyst decision event for a contradiction."""

    __tablename__ = "claim_contradiction_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contradiction_id: Mapped[str] = mapped_column(
        ForeignKey("claim_contradictions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    selected_claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytic_claims.id", ondelete="SET NULL"), index=True
    )
    comment: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
