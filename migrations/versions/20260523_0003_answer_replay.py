"""agent answer replay metadata

Revision ID: 20260523_0003
Revises: 20260523_0002
Create Date: 2026-05-23 00:40:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0003"
down_revision: str | None = "20260523_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = _columns()
    if "prompt_version" not in columns:
        op.add_column("agent_answers", sa.Column("prompt_version", sa.String(length=120), nullable=True))
    if "model_id" not in columns:
        op.add_column("agent_answers", sa.Column("model_id", sa.Text(), nullable=True))
    if "replay_of_answer_id" not in columns:
        op.add_column("agent_answers", sa.Column("replay_of_answer_id", sa.String(), nullable=True))
    op.execute("UPDATE agent_answers SET prompt_version = 'datarules_answer_v1' WHERE prompt_version IS NULL")
    op.execute("UPDATE agent_answers SET model_id = model_source WHERE model_id IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_answers_replay_of_answer_id ON agent_answers(replay_of_answer_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_answers_replay_of_answer_id")
    columns = _columns()
    if "replay_of_answer_id" in columns:
        op.drop_column("agent_answers", "replay_of_answer_id")
    if "model_id" in columns:
        op.drop_column("agent_answers", "model_id")
    if "prompt_version" in columns:
        op.drop_column("agent_answers", "prompt_version")


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("agent_answers")}
