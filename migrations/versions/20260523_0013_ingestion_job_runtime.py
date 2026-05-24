"""ingestion job runtime metadata

Revision ID: 20260523_0013
Revises: 20260523_0012
Create Date: 2026-05-24 04:55:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0013"
down_revision: str | None = "20260523_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not _table_exists("ingestion_jobs"):
        return
    _add_column("attempt_count", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column("max_attempts", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    _add_column("heartbeat_at", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for name in ("heartbeat_at", "max_attempts", "attempt_count"):
        if _column_exists(name):
            op.drop_column("ingestion_jobs", name)


def _add_column(name: str, column: sa.Column) -> None:
    if not _column_exists(name):
        op.add_column("ingestion_jobs", column)


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_exists(name: str) -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("ingestion_jobs")
    return any(column["name"] == name for column in columns)
