"""persistent intelligence profiles and pgvector

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "channel_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("subscribers", sa.BigInteger(), nullable=True),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_channel_profiles_username", "channel_profiles", ["username"], unique=True)
    op.create_table(
        "channel_profile_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_post_count", sa.Integer(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("content_dna_json", sa.JSON(), nullable=False),
        sa.Column("component_vectors_json", sa.JSON(), nullable=False),
        sa.Column("embedding", Vector(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["channel_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "version", name="uq_profile_version"),
    )
    op.create_index("ix_channel_profile_versions_profile_id", "channel_profile_versions", ["profile_id"])
    op.execute("CREATE INDEX ix_profile_embedding_hnsw ON channel_profile_versions USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.drop_index("ix_profile_embedding_hnsw", table_name="channel_profile_versions")
    op.drop_index("ix_channel_profile_versions_profile_id", table_name="channel_profile_versions")
    op.drop_table("channel_profile_versions")
    op.drop_index("ix_channel_profiles_username", table_name="channel_profiles")
    op.drop_table("channel_profiles")
