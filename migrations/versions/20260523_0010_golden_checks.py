"""golden answer checks

Revision ID: 20260523_0010
Revises: 20260523_0009
Create Date: 2026-05-24 03:50:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0010"
down_revision: str | None = "20260523_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        "golden_checks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_terms", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("last_result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_golden_checks_dataset_id", "golden_checks", ["dataset_id"])


def downgrade() -> None:
    if _table_exists():
        op.drop_index("ix_golden_checks_dataset_id", table_name="golden_checks")
        op.drop_table("golden_checks")


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("golden_checks")
