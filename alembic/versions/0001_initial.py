"""initial schema

Revision ID: 0001
Revises:
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_username", sa.String(length=128), nullable=False),
        sa.Column("analysis_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_step", sa.Integer(), nullable=False),
        sa.Column("progress_text", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report_path", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_jobs")),
    )
    op.create_index(op.f("ix_analysis_jobs_channel_username"), "analysis_jobs", ["channel_username"])
    op.create_index(op.f("ix_analysis_jobs_status"), "analysis_jobs", ["status"])
    op.create_index(op.f("ix_analysis_jobs_telegram_user_id"), "analysis_jobs", ["telegram_user_id"])
    op.create_table(
        "posts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("reactions", sa.Integer(), nullable=True),
        sa.Column("forwards", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], name=op.f("fk_posts_job_id_analysis_jobs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
        sa.UniqueConstraint("job_id", "message_id", name="uq_posts_job_message"),
    )
    op.create_index(op.f("ix_posts_job_id"), "posts", ["job_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_posts_job_id"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_analysis_jobs_telegram_user_id"), table_name="analysis_jobs")
    op.drop_index(op.f("ix_analysis_jobs_status"), table_name="analysis_jobs")
    op.drop_index(op.f("ix_analysis_jobs_channel_username"), table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
