"""golden profile library

Revision ID: 20260523_0011
Revises: 20260523_0010
Create Date: 2026-05-24 04:05:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0011"
down_revision: str | None = "20260523_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        "golden_profiles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_golden_profiles_domain", "golden_profiles", ["domain"])


def downgrade() -> None:
    if _table_exists():
        op.drop_index("ix_golden_profiles_domain", table_name="golden_profiles")
        op.drop_table("golden_profiles")


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("golden_profiles")
