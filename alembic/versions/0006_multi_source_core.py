"""multi source core

Revision ID: 0006_multi_source_core
Revises: 0005_monitoring_alerts
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_multi_source_core"
down_revision: str | None = "0005_monitoring_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=1024), nullable=False),
        sa.Column("display_name", sa.String(length=512)),
        sa.Column("adapter_name", sa.String(length=128), nullable=False),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_type", "external_id", name="uq_source_type_external_id"),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_sources_last_success_at", "sources", ["last_success_at"])
    op.create_index("ix_sources_last_error_at", "sources", ["last_error_at"])

    op.create_table(
        "source_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_source_runs_source_id", "source_runs", ["source_id"])
    op.create_index("ix_source_runs_status", "source_runs", ["status"])
    op.create_index("ix_source_runs_finished_at", "source_runs", ["finished_at"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), sa.ForeignKey("source_runs.id", ondelete="SET NULL")),
        sa.Column("external_document_id", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=512)),
        sa.Column("language", sa.String(length=16)),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_document_id", name="uq_source_external_document"),
        sa.UniqueConstraint("fingerprint", name="uq_source_document_fingerprint"),
    )
    for column in ("source_id", "source_run_id", "language", "published_at", "fingerprint", "content_fingerprint"):
        op.create_index(f"ix_source_documents_{column}", "source_documents", [column])

    op.create_table(
        "source_errors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), sa.ForeignKey("source_runs.id", ondelete="SET NULL")),
        sa.Column("error_type", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("source_id", "source_run_id", "error_type", "occurred_at"):
        op.create_index(f"ix_source_errors_{column}", "source_errors", [column])


def downgrade() -> None:
    op.drop_table("source_errors")
    op.drop_table("source_documents")
    op.drop_table("source_runs")
    op.drop_table("sources")
