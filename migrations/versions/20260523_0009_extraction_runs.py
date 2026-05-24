"""document extraction run history

Revision ID: 20260523_0009
Revises: 20260523_0008
Create Date: 2026-05-24 02:30:00 UTC
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0009"
down_revision: str | None = "20260523_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        "document_extraction_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("run_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("canonical_path", sa.Text(), nullable=False),
        sa.Column("quality_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_document_extraction_runs_dataset_id", "document_extraction_runs", ["dataset_id"])
    op.create_index("ix_document_extraction_runs_document_id", "document_extraction_runs", ["document_id"])


def downgrade() -> None:
    if _table_exists():
        op.drop_index("ix_document_extraction_runs_document_id", table_name="document_extraction_runs")
        op.drop_index("ix_document_extraction_runs_dataset_id", table_name="document_extraction_runs")
        op.drop_table("document_extraction_runs")


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("document_extraction_runs")
