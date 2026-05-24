"""golden evaluation run history

Revision ID: 20260523_0012
Revises: 20260523_0011
Create Date: 2026-05-24 04:12:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0012"
down_revision: str | None = "20260523_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        "golden_evaluation_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_golden_evaluation_runs_dataset_id", "golden_evaluation_runs", ["dataset_id"])
    op.create_index("ix_golden_evaluation_runs_profile_id", "golden_evaluation_runs", ["profile_id"])


def downgrade() -> None:
    if _table_exists():
        op.drop_index("ix_golden_evaluation_runs_profile_id", table_name="golden_evaluation_runs")
        op.drop_index("ix_golden_evaluation_runs_dataset_id", table_name="golden_evaluation_runs")
        op.drop_table("golden_evaluation_runs")


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("golden_evaluation_runs")
