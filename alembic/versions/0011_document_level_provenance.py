"""document-level provenance

Revision ID: 0011_document_level_provenance
Revises: 0010_evidence_provenance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_document_level_provenance"
down_revision: Union[str, None] = "0010_evidence_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence_references", sa.Column("document_id", sa.String(length=36), nullable=True))
    op.add_column("evidence_references", sa.Column("source_type", sa.String(length=32), nullable=True))
    op.add_column("evidence_references", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column("evidence_references", sa.Column("author", sa.String(length=512), nullable=True))
    op.add_column("evidence_references", sa.Column("excerpt", sa.Text(), nullable=True))
    op.add_column("evidence_references", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_references", sa.Column("fingerprint", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_evidence_source_document", "evidence_references", "source_documents",
        ["document_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_evidence_document_id", "evidence_references", ["document_id"])
    op.create_index("ix_evidence_source_type", "evidence_references", ["source_type"])
    op.create_index("ix_evidence_published_at", "evidence_references", ["published_at"])
    op.create_index("ix_evidence_fingerprint", "evidence_references", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_evidence_fingerprint", table_name="evidence_references")
    op.drop_index("ix_evidence_published_at", table_name="evidence_references")
    op.drop_index("ix_evidence_source_type", table_name="evidence_references")
    op.drop_index("ix_evidence_document_id", table_name="evidence_references")
    op.drop_constraint("fk_evidence_source_document", "evidence_references", type_="foreignkey")
    for column in ("fingerprint", "published_at", "excerpt", "author", "canonical_url", "source_type", "document_id"):
        op.drop_column("evidence_references", column)
