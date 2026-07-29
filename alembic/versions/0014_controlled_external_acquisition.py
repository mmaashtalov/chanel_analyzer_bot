"""Controlled external evidence acquisition.

Revision ID: 0014_controlled_external_acquisition
Revises: 0013_evidence_acquisition
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_controlled_external_acquisition"
down_revision = "0013_evidence_acquisition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_requests", sa.Column("collection_summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("evidence_requests", sa.Column("last_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("evidence_requests", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.create_index("ix_evidence_requests_last_attempt_at", "evidence_requests", ["last_attempt_at"])
    op.create_index("ix_evidence_requests_next_attempt_at", "evidence_requests", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_evidence_requests_next_attempt_at", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_last_attempt_at", table_name="evidence_requests")
    op.drop_column("evidence_requests", "next_attempt_at")
    op.drop_column("evidence_requests", "last_attempt_at")
    op.drop_column("evidence_requests", "collection_summary_json")
