"""audit events

Revision ID: 20260523_0004
Revises: 20260523_0003
Create Date: 2026-05-23 22:00:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0004"
down_revision: str | None = "20260523_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = sa.Table(
        "audit_events",
        sa.MetaData(),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    table.create(op.get_bind(), checkfirst=True)
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_dataset_id ON audit_events(dataset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_action ON audit_events(action)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_events_action")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_dataset_id")
    op.drop_table("audit_events", if_exists=True)
