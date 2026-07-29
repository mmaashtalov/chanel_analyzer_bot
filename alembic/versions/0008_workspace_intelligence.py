"""workspace intelligence snapshots

Revision ID: 0008_workspace_intelligence
Revises: 0007_intelligence_workspaces
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_workspace_intelligence"
down_revision: Union[str, None] = "0007_intelligence_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_intelligence_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("coverage_status", sa.String(length=16), nullable=False),
        sa.Column("coverage_ratio", sa.Float(), nullable=False),
        sa.Column("analyzed_channel_count", sa.Integer(), nullable=False),
        sa.Column("total_posts", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("report_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_intelligence_workspace", "workspace_intelligence_snapshots", ["workspace_id"])
    op.create_index("ix_workspace_intelligence_generated", "workspace_intelligence_snapshots", ["generated_at"])
    op.create_index("ix_workspace_intelligence_coverage", "workspace_intelligence_snapshots", ["coverage_status"])


def downgrade() -> None:
    op.drop_index("ix_workspace_intelligence_coverage", table_name="workspace_intelligence_snapshots")
    op.drop_index("ix_workspace_intelligence_generated", table_name="workspace_intelligence_snapshots")
    op.drop_index("ix_workspace_intelligence_workspace", table_name="workspace_intelligence_snapshots")
    op.drop_table("workspace_intelligence_snapshots")
