"""Monitoring and alerts

Revision ID: 0005_monitoring_alerts
Revises: 0004_evolution_engine
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_monitoring_alerts"
down_revision = "0004_evolution_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_username", sa.String(128), nullable=False),
        sa.Column("sensitivity", sa.String(16), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_profile_version", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("telegram_user_id", "channel_username", name="uq_watch_user_channel"),
    )
    for column in ("telegram_user_id", "chat_id", "channel_username", "last_checked_at", "next_check_at"):
        op.create_index(f"ix_watchlists_{column}", "watchlists", [column])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("watchlist_id", sa.String(36), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_username", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_message_ids", sa.JSON(), nullable=False),
        sa.Column("event_fingerprint", sa.String(64), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("watchlist_id", "event_fingerprint", name="uq_watch_alert_fingerprint"),
    )
    for column in ("watchlist_id", "telegram_user_id", "channel_username", "severity", "category", "delivered_at", "read_at", "created_at"):
        op.create_index(f"ix_alert_events_{column}", "alert_events", [column])

    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_event_id", sa.String(36), sa.ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("alert_event_id", "chat_id", "status"):
        op.create_index(f"ix_alert_deliveries_{column}", "alert_deliveries", [column])


def downgrade() -> None:
    op.drop_table("alert_deliveries")
    op.drop_table("alert_events")
    op.drop_table("watchlists")
