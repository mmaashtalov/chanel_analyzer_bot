"""Source independence and corroboration.

Revision ID: 0015_source_independence
Revises: 0014_controlled_external_acquisition
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_source_independence"
down_revision = "0014_controlled_external_acquisition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analytic_claims", sa.Column("independence_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("analytic_claims", sa.Column("corroboration_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("analytic_claims", sa.Column("corroboration_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("analytic_claims", "corroboration_json")
    op.drop_column("analytic_claims", "corroboration_score")
    op.drop_column("analytic_claims", "independence_score")
