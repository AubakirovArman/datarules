"""agent answer history

Revision ID: 20260523_0002
Revises: 20260523_0001
Create Date: 2026-05-23 00:20:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0002"
down_revision: str | None = "20260523_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    metadata = sa.MetaData()
    sa.Table("datasets", metadata, sa.Column("id", sa.String(), primary_key=True))
    table = sa.Table(
        "agent_answers",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=40), nullable=False),
        sa.Column("retrieval_mode", sa.String(length=80), nullable=False),
        sa.Column("model_source", sa.String(length=120), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    table.create(op.get_bind(), checkfirst=True)
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_answers_dataset_id ON agent_answers(dataset_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_answers_dataset_id")
    op.drop_table("agent_answers", if_exists=True)
