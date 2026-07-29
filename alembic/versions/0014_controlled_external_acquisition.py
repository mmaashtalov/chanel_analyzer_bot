"""Controlled external evidence acquisition.

Revision ID: 0014_controlled_external_acquisition
Revises: 0013_evidence_acquisition
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_controlled_external_acquisition"
down_revision = "0013_evidence_acquisition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic creates version_num as VARCHAR(32) by default. This revision and
    # subsequent descriptive revision IDs are longer, so widen the service
    # column before Alembic records the new revision at the end of this step.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.add_column(
        "evidence_requests",
        sa.Column(
            "collection_summary_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "evidence_requests",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "evidence_requests",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_evidence_requests_last_attempt_at",
        "evidence_requests",
        ["last_attempt_at"],
    )
    op.create_index(
        "ix_evidence_requests_next_attempt_at",
        "evidence_requests",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_requests_next_attempt_at", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_last_attempt_at", table_name="evidence_requests")
    op.drop_column("evidence_requests", "next_attempt_at")
    op.drop_column("evidence_requests", "last_attempt_at")
    op.drop_column("evidence_requests", "collection_summary_json")
    # Keep alembic_version at VARCHAR(128): shrinking while it contains this
    # revision ID would fail before Alembic can record the previous revision.
