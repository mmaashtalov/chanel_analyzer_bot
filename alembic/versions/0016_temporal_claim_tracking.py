"""Temporal claim tracking and contradiction resolution.

Revision ID: 0016_temporal_claim_tracking
Revises: 0015_source_independence
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_temporal_claim_tracking"
down_revision = "0015_source_independence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analytic_claims", sa.Column("claim_identity_id", sa.String(length=40), nullable=True))
    op.add_column("analytic_claims", sa.Column("temporal_status", sa.String(length=24), nullable=False, server_default="current"))
    op.create_index("ix_analytic_claims_claim_identity_id", "analytic_claims", ["claim_identity_id"])
    op.create_index("ix_analytic_claims_temporal_status", "analytic_claims", ["temporal_status"])
    op.create_table(
        "claim_identities",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("canonical_statement", sa.Text(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_identities_workspace_id", "claim_identities", ["workspace_id"])
    op.create_index("ix_claim_identities_category", "claim_identities", ["category"])
    op.create_table(
        "claim_timeline_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_identity_id", sa.String(length=40), sa.ForeignKey("claim_identities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_claim_id", sa.String(length=80), sa.ForeignKey("analytic_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_claim_id", sa.String(length=80), sa.ForeignKey("analytic_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(length=24), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_claim_id", "target_claim_id", "relation_type", name="uq_claim_timeline_relation"),
    )
    for column in ("workspace_id", "claim_identity_id", "source_claim_id", "target_claim_id", "relation_type", "event_hash"):
        op.create_index(f"ix_claim_timeline_links_{column}", "claim_timeline_links", [column])


def downgrade() -> None:
    op.drop_table("claim_timeline_links")
    op.drop_table("claim_identities")
    op.drop_index("ix_analytic_claims_temporal_status", table_name="analytic_claims")
    op.drop_index("ix_analytic_claims_claim_identity_id", table_name="analytic_claims")
    op.drop_column("analytic_claims", "temporal_status")
    op.drop_column("analytic_claims", "claim_identity_id")
