"""connection url encryption

Revision ID: 20260523_0005
Revises: 20260523_0004
Create Date: 2026-05-23 23:10:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0005"
down_revision: str | None = "20260523_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "sqlalchemy_url_encrypted" not in _columns():
        op.add_column("database_connections", sa.Column("sqlalchemy_url_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    if "sqlalchemy_url_encrypted" in _columns():
        op.drop_column("database_connections", "sqlalchemy_url_encrypted")


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("database_connections")}
