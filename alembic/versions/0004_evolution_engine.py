"""Evolution Engine

Revision ID: 0004_evolution_engine
Revises: 0003_intelligence_graph
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_evolution_engine"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_changes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("channel_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_username", sa.String(length=128), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=False),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("evidence_message_ids", sa.JSON(), nullable=False),
        sa.Column("event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "from_version", "to_version", "event_fingerprint", name="uq_profile_change_event"),
    )
    for column in ("profile_id", "channel_username", "event_type", "category", "severity", "created_at"):
        op.create_index(f"ix_profile_changes_{column}", "profile_changes", [column])


def downgrade() -> None:
    op.drop_table("profile_changes")
