"""baseline schema

Revision ID: 20260523_0001
Revises:
Create Date: 2026-05-23 00:00:00 UTC
"""

from collections.abc import Sequence

from alembic import op

from datarules_api import models  # noqa: F401
from datarules_api.db import Base

revision: str = "20260523_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
