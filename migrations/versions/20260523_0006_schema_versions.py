"""schema versions

Revision ID: 20260523_0006
Revises: 20260523_0005
Create Date: 2026-05-23 23:40:00 UTC
"""

from collections.abc import Sequence

from alembic import op

from datarules_api import models  # noqa: F401
from datarules_api.db import Base

revision: str = "20260523_0006"
down_revision: str | None = "20260523_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("schema_versions", if_exists=True)
