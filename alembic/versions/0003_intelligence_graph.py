"""intelligence graph

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity_type", "canonical_name", name="uq_entity_type_name"),
    )
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])
    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(512), nullable=False),
        sa.UniqueConstraint("entity_id", "alias", name="uq_entity_alias"),
    )
    op.create_index("ix_entity_aliases_entity_id", "entity_aliases", ["entity_id"])
    op.create_index("ix_entity_aliases_alias", "entity_aliases", ["alias"])
    op.create_table(
        "graph_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("channel_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("relationship_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "profile_version", name="uq_graph_profile_version"),
    )
    op.create_index("ix_graph_snapshots_profile_id", "graph_snapshots", ["profile_id"])
    op.create_index("ix_graph_snapshots_collected_at", "graph_snapshots", ["collected_at"])
    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("graph_snapshot_id", sa.String(36), sa.ForeignKey("graph_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_username", sa.String(128), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.UniqueConstraint("graph_snapshot_id", "entity_id", "message_id", name="uq_graph_entity_message"),
    )
    for name, columns in {
        "ix_entity_mentions_graph_snapshot_id": ["graph_snapshot_id"],
        "ix_entity_mentions_entity_id": ["entity_id"],
        "ix_entity_mentions_channel_username": ["channel_username"],
        "ix_entity_mentions_published_at": ["published_at"],
    }.items():
        op.create_index(name, "entity_mentions", columns)
    op.create_table(
        "relationships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("graph_snapshot_id", sa.String(36), sa.ForeignKey("graph_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(256), nullable=False),
        sa.Column("target_entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_message_ids", sa.JSON(), nullable=False),
        sa.UniqueConstraint("graph_snapshot_id", "target_entity_id", "relation_type", name="uq_graph_target_relation"),
    )
    for name, columns in {
        "ix_relationships_graph_snapshot_id": ["graph_snapshot_id"],
        "ix_relationships_source_name": ["source_name"],
        "ix_relationships_target_entity_id": ["target_entity_id"],
        "ix_relationships_relation_type": ["relation_type"],
    }.items():
        op.create_index(name, "relationships", columns)


def downgrade() -> None:
    op.drop_table("relationships")
    op.drop_table("entity_mentions")
    op.drop_table("graph_snapshots")
    op.drop_table("entity_aliases")
    op.drop_table("entities")
