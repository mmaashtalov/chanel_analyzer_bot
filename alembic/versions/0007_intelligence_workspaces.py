"""intelligence workspaces

Revision ID: 0007_intelligence_workspaces
Revises: 0006_multi_source_core
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0007_intelligence_workspaces"
down_revision: str | None = "0006_multi_source_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("name_key", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("telegram_user_id", "name_key", name="uq_workspace_user_name"))
    op.create_index("ix_workspaces_telegram_user_id", "workspaces", ["telegram_user_id"])
    op.create_table("workspace_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("value", sa.String(1024), nullable=False),
        sa.Column("normalized_value", sa.String(1024), nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "item_type", "normalized_value", name="uq_workspace_item"))
    for column in ("workspace_id", "item_type", "normalized_value"):
        op.create_index(f"ix_workspace_items_{column}", "workspace_items", [column])


def downgrade() -> None:
    op.drop_table("workspace_items")
    op.drop_table("workspaces")
