"""Link evidence-first provenance bundles to Workspaces.

Revision ID: 0018_workspace_provenance_links
Revises: 0017_contradiction_triage
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_workspace_provenance_links"
down_revision = "0017_contradiction_triage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_provenance_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bundle_id",
            sa.String(length=80),
            sa.ForeignKey("provenance_bundles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(length=32), nullable=False, server_default="channel_analysis"),
        sa.Column("source_item", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "bundle_id", name="uq_workspace_provenance_link"),
    )
    op.create_index(
        "ix_workspace_provenance_links_workspace_id",
        "workspace_provenance_links",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_provenance_links_bundle_id",
        "workspace_provenance_links",
        ["bundle_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_provenance_links_bundle_id",
        table_name="workspace_provenance_links",
    )
    op.drop_index(
        "ix_workspace_provenance_links_workspace_id",
        table_name="workspace_provenance_links",
    )
    op.drop_table("workspace_provenance_links")
