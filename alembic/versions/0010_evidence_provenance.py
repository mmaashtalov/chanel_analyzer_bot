"""evidence and provenance engine

Revision ID: 0010_evidence_provenance
Revises: 0009_workspace_evolution
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_evidence_provenance"
down_revision: Union[str, None] = "0009_workspace_evolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provenance_bundles",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("completeness", sa.Float(), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
        sa.Column("bundle_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integrity_hash"),
    )
    op.create_index("ix_provenance_subject_type", "provenance_bundles", ["subject_type"])
    op.create_index("ix_provenance_subject_id", "provenance_bundles", ["subject_id"])
    op.create_index("ix_provenance_integrity_hash", "provenance_bundles", ["integrity_hash"])

    op.create_table(
        "analytic_claims",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("bundle_id", sa.String(length=80), nullable=False),
        sa.Column("claim_index", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("assessment", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_quality", sa.Float(), nullable=False),
        sa.Column("caveats_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["provenance_bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "claim_index", name="uq_claim_bundle_index"),
    )
    op.create_index("ix_claim_bundle", "analytic_claims", ["bundle_id"])
    op.create_index("ix_claim_category", "analytic_claims", ["category"])
    op.create_index("ix_claim_severity", "analytic_claims", ["severity"])

    op.create_table(
        "evidence_references",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("bundle_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("locator", sa.String(length=512), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("strength", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["provenance_bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_bundle", "evidence_references", ["bundle_id"])
    op.create_index("ix_evidence_kind", "evidence_references", ["kind"])
    op.create_index("ix_evidence_source", "evidence_references", ["source_id"])
    op.create_index("ix_evidence_content_hash", "evidence_references", ["content_hash"])

    op.create_table(
        "claim_evidence_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.String(length=80), nullable=False),
        sa.Column("evidence_id", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["analytic_claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_references.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_link"),
    )
    op.create_index("ix_link_claim", "claim_evidence_links", ["claim_id"])
    op.create_index("ix_link_evidence", "claim_evidence_links", ["evidence_id"])


def downgrade() -> None:
    op.drop_table("claim_evidence_links")
    op.drop_table("evidence_references")
    op.drop_table("analytic_claims")
    op.drop_table("provenance_bundles")
