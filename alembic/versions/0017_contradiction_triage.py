"""Contradiction triage queue and append-only resolution events.

Revision ID: 0017_contradiction_triage
Revises: 0016_temporal_claim_tracking
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_contradiction_triage"
down_revision = "0016_temporal_claim_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claim_identities",
        sa.Column(
            "canonical_claim_id",
            sa.String(length=80),
            sa.ForeignKey("analytic_claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_claim_identities_canonical_claim_id",
        "claim_identities",
        ["canonical_claim_id"],
    )

    op.create_table(
        "claim_contradictions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "claim_identity_id",
            sa.String(length=40),
            sa.ForeignKey("claim_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_claim_id",
            sa.String(length=80),
            sa.ForeignKey("analytic_claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_claim_id",
            sa.String(length=80),
            sa.ForeignKey("analytic_claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("resolution_action", sa.String(length=32), nullable=True),
        sa.Column(
            "selected_claim_id",
            sa.String(length=80),
            sa.ForeignKey("analytic_claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolution_comment", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "source_claim_id", "target_claim_id",
            name="uq_claim_contradiction_pair",
        ),
    )
    for column in (
        "workspace_id",
        "claim_identity_id",
        "source_claim_id",
        "target_claim_id",
        "severity",
        "status",
        "resolution_action",
        "selected_claim_id",
        "resolved_by",
        "active",
    ):
        op.create_index(f"ix_claim_contradictions_{column}", "claim_contradictions", [column])

    op.create_table(
        "claim_contradiction_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "contradiction_id",
            sa.String(length=64),
            sa.ForeignKey("claim_contradictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column(
            "selected_claim_id",
            sa.String(length=80),
            sa.ForeignKey("analytic_claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "contradiction_id",
        "telegram_user_id",
        "action",
        "new_status",
        "selected_claim_id",
        "previous_event_hash",
        "event_hash",
    ):
        op.create_index(
            f"ix_claim_contradiction_events_{column}",
            "claim_contradiction_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("claim_contradiction_events")
    op.drop_table("claim_contradictions")
    op.drop_index(
        "ix_claim_identities_canonical_claim_id",
        table_name="claim_identities",
    )
    op.drop_column("claim_identities", "canonical_claim_id")
