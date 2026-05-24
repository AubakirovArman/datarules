"""load plan schema version reference

Revision ID: 20260523_0007
Revises: 20260523_0006
Create Date: 2026-05-23 23:55:00 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_0007"
down_revision: str | None = "20260523_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "schema_version_id" not in _columns():
        op.add_column("load_plans", sa.Column("schema_version_id", sa.String(), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_load_plans_schema_version_id ON load_plans(schema_version_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_load_plans_schema_version_id")
    if "schema_version_id" in _columns():
        op.drop_column("load_plans", "schema_version_id")


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("load_plans")}
