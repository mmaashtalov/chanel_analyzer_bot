"""analyst verification and evidence gaps

Revision ID: 0012_analyst_verification
Revises: 0011_document_level_provenance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_analyst_verification"
down_revision: Union[str, None] = "0011_document_level_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("provenance_bundles", sa.Column("review_completeness", sa.Float(), nullable=False, server_default="0"))
    op.add_column("analytic_claims", sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"))
    op.add_column("analytic_claims", sa.Column("reviewed_by", sa.BigInteger(), nullable=True))
    op.add_column("analytic_claims", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analytic_claims", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column("analytic_claims", sa.Column("review_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_claim_review_status", "analytic_claims", ["review_status"])
    op.create_index("ix_claim_reviewed_by", "analytic_claims", ["reviewed_by"])
    op.create_table(
        "claim_review_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=80), nullable=False),
        sa.Column("bundle_id", sa.String(length=80), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["provenance_bundles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["analytic_claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_hash"),
    )
    op.create_index("ix_claim_review_events_claim_id", "claim_review_events", ["claim_id"])
    op.create_index("ix_claim_review_events_bundle_id", "claim_review_events", ["bundle_id"])
    op.create_index("ix_claim_review_events_user", "claim_review_events", ["telegram_user_id"])
    op.create_index("ix_claim_review_events_status", "claim_review_events", ["new_status"])


def downgrade() -> None:
    op.drop_table("claim_review_events")
    op.drop_index("ix_claim_reviewed_by", table_name="analytic_claims")
    op.drop_index("ix_claim_review_status", table_name="analytic_claims")
    for column in ("review_version", "review_comment", "reviewed_at", "reviewed_by", "review_status"):
        op.drop_column("analytic_claims", column)
    op.drop_column("provenance_bundles", "review_completeness")
