"""workspace evolution reports

Revision ID: 0009_workspace_evolution
Revises: 0008_workspace_intelligence
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0009_workspace_evolution"
down_revision: Union[str, None] = "0008_workspace_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_evolution_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("baseline_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("current_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("baseline_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trend", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("report_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_snapshot_id"], ["workspace_intelligence_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_snapshot_id"], ["workspace_intelligence_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "baseline_snapshot_id", "current_snapshot_id", name="uq_workspace_evolution_pair"),
    )
    op.create_index("ix_workspace_evolution_workspace", "workspace_evolution_reports", ["workspace_id"])
    op.create_index("ix_workspace_evolution_trend", "workspace_evolution_reports", ["trend"])


def downgrade() -> None:
    op.drop_index("ix_workspace_evolution_trend", table_name="workspace_evolution_reports")
    op.drop_index("ix_workspace_evolution_workspace", table_name="workspace_evolution_reports")
    op.drop_table("workspace_evolution_reports")
