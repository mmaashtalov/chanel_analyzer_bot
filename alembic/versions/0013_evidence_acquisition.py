"""Evidence acquisition orchestration.

Revision ID: 0013_evidence_acquisition
Revises: 0012_analyst_verification
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_evidence_acquisition"
down_revision = "0012_analyst_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("evidence_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_id", sa.String(80), sa.ForeignKey("analytic_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("gap_codes_json", sa.JSON(), nullable=False), sa.Column("query_terms_json", sa.JSON(), nullable=False),
        sa.Column("source_plan_json", sa.JSON(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False), sa.Column("documents_collected", sa.Integer(), nullable=False),
        sa.Column("documents_linked", sa.Integer(), nullable=False), sa.Column("last_error", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_evidence_requests_workspace_id", "evidence_requests", ["workspace_id"])
    op.create_index("ix_evidence_requests_claim_id", "evidence_requests", ["claim_id"])
    op.create_index("ix_evidence_requests_user", "evidence_requests", ["telegram_user_id"])
    op.create_index("ix_evidence_requests_status", "evidence_requests", ["status"])
    op.create_table("evidence_request_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("evidence_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_status", sa.String(32)), sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False), sa.Column("event_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_evidence_request_events_request", "evidence_request_events", ["request_id"])
    op.create_index("ix_evidence_request_events_status", "evidence_request_events", ["new_status"])


def downgrade() -> None:
    op.drop_table("evidence_request_events")
    op.drop_table("evidence_requests")
