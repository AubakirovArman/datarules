import json
import re
from typing import Any

from sqlalchemy import text

from .models import LoadPlan
from .parsers.common import clean_text
from .row_identity import stable_row_id
from .row_review import normalize_row_status, row_is_loadable
from .typed_values import sql_type, sql_value

BASE_COLUMNS = {
    "id": "text PRIMARY KEY",
    "content": "text NOT NULL",
    "source_document_id": "text NOT NULL",
    "source_block_id": "text NOT NULL",
    "source_file": "text",
    "page": "integer",
    "sheet": "text",
    "confidence": "double precision",
    "field_values": "jsonb NOT NULL DEFAULT '{}'::jsonb",
    "field_sources": "jsonb NOT NULL DEFAULT '{}'::jsonb",
    "metadata": "jsonb NOT NULL DEFAULT '{}'::jsonb",
    "created_at": "timestamptz NOT NULL DEFAULT now()",
}


def write_target_rows(conn: Any, schema: str, plan: LoadPlan) -> int:
    if plan.target_mode == "new":
        _create_target_table(conn, schema, plan.target_table, plan.schema_json)
        _ensure_managed_columns(conn, schema, plan.target_table)
    existing_columns = _table_columns(conn, schema, plan.target_table)
    column_types = _schema_column_types(plan.schema_json)
    _require_source_columns(existing_columns)
    inserted = 0
    for row in plan.preview_rows:
        if not row_is_loadable(row):
            continue
        _insert_row(conn, schema, plan.target_table, row, existing_columns, column_types)
        inserted += 1
    return inserted


def _create_target_table(conn: Any, schema: str, table: str, schema_json: dict[str, Any]) -> None:
    parts = [f"{_qi(name)} {definition}" for name, definition in BASE_COLUMNS.items()]
    for column in schema_json.get("target_columns", []):
        name = _safe_column(str(column.get("name", "")))
        if name and name not in BASE_COLUMNS:
            parts.append(f"{_qi(name)} {sql_type(str(column.get('type', 'text')))}")
    conn.execute(text(f"CREATE TABLE IF NOT EXISTS {_qi(schema)}.{_qi(table)} ({', '.join(parts)})"))
    conn.execute(
        text(
            f"COMMENT ON TABLE {_qi(schema)}.{_qi(table)} "
            "IS 'Created by DataRules after user-approved structured extraction.'"
        )
    )


def _insert_row(
    conn: Any,
    schema: str,
    table: str,
    row: dict[str, Any],
    existing_columns: set[str],
    column_types: dict[str, str],
) -> None:
    field_values = row.get("field_values") if isinstance(row.get("field_values"), dict) else {}
    field_sources = row.get("field_sources") if isinstance(row.get("field_sources"), dict) else {}
    values = {
        "id": stable_row_id(row),
        "content": clean_text(str(row.get("content") or row.get("field_text") or "")),
        "source_document_id": row.get("source_document_id"),
        "source_block_id": row.get("source_block_id"),
        "source_file": row.get("source_file"),
        "page": row.get("page"),
        "sheet": row.get("sheet"),
        "confidence": row.get("confidence"),
        "field_values": json.dumps(field_values, ensure_ascii=False, default=str),
        "field_sources": json.dumps(field_sources, ensure_ascii=False, default=str),
        "metadata": json.dumps(
            {
                "extraction_source": row.get("extraction_source"),
                "row_status": normalize_row_status(row),
                "field_sources": field_sources,
                "validation_errors": row.get("validation_errors", []),
            },
            ensure_ascii=False,
            default=str,
        ),
    }
    for key, value in field_values.items():
        safe_key = _safe_column(str(key))
        if safe_key in existing_columns:
            typed, error = sql_value(value, column_types.get(safe_key, "text"))
            if error:
                raise ValueError(f"Invalid value for {safe_key}: {error}")
            values[safe_key] = typed
    columns = [column for column in values if column in existing_columns]
    params = {column: values[column] for column in columns}
    assignments = ", ".join(f"{_qi(column)} = excluded.{_qi(column)}" for column in columns if column != "id")
    conn.execute(
        text(
            f"INSERT INTO {_qi(schema)}.{_qi(table)} "
            f"({', '.join(_qi(column) for column in columns)}) "
            f"VALUES ({', '.join(':' + column for column in columns)}) "
            f"ON CONFLICT (id) DO UPDATE SET {assignments}"
        ),
        params,
    )


def _table_columns(conn: Any, schema: str, table: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            """
        ),
        {"schema": schema, "table": table},
    )
    return {row[0] for row in rows}


def _ensure_managed_columns(conn: Any, schema: str, table: str) -> None:
    columns = _table_columns(conn, schema, table)
    if "field_sources" not in columns:
        conn.execute(text(f"ALTER TABLE {_qi(schema)}.{_qi(table)} ADD COLUMN field_sources jsonb NOT NULL DEFAULT '{{}}'::jsonb"))


def _require_source_columns(columns: set[str]) -> None:
    required = {"id", "content", "source_document_id", "source_block_id", "field_values"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Target table is missing DataRules source columns: {', '.join(missing)}")


def _schema_column_types(schema_json: dict[str, Any]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for column in schema_json.get("target_columns", []):
        name = _safe_column(str(column.get("name", "")))
        if name:
            rows[name] = str(column.get("type") or "text")
    return rows


def _safe_column(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return safe[:63]


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
