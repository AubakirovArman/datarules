"""agent answer grounding metadata

Revision ID: 20260523_0008
Revises: 20260523_0007
Create Date: 2026-05-24 01:20:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0008"
down_revision: str | None = "20260523_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "grounding_json" not in _columns():
        op.add_column("agent_answers", sa.Column("grounding_json", sa.JSON(), nullable=True))
    op.execute("UPDATE agent_answers SET grounding_json = '{}' WHERE grounding_json IS NULL")


def downgrade() -> None:
    if "grounding_json" in _columns():
        op.drop_column("agent_answers", "grounding_json")


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("agent_answers")}
