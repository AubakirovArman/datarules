import re
from typing import Any

from sqlalchemy import create_engine, text

from .connection_urls import connection_url
from .models import DatabaseConnection
from .typed_values import sql_type

REQUIRED_SOURCE_COLUMNS = {"id", "content", "source_document_id", "source_block_id", "field_values"}


def target_compatibility_issues(
    connection: DatabaseConnection | None,
    schema_name: str,
    target_mode: str,
    target_table: str,
    schema_json: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if target_mode != "existing" or not connection:
        return []
    live, error = _live_columns(connection, schema_name, target_table)
    if error:
        return [error]
    columns = set(live)
    if not columns:
        return [_issue("target_table_missing_live", "Selected target table is not present in the connected database.")]
    issues: list[dict[str, Any]] = []
    missing_sources = sorted(REQUIRED_SOURCE_COLUMNS - columns)
    if missing_sources:
        issues.append(_issue(
            "target_missing_source_columns",
            "Existing table is missing DataRules managed source columns.",
            columns=missing_sources,
        ))
    missing_data = _missing_schema_columns(columns, schema_json or {})
    if missing_data:
        issues.append(_issue(
            "target_missing_data_columns",
            "Existing table is missing columns required by the approved load schema.",
            columns=missing_data,
        ))
    mismatches = _type_mismatches(live, schema_json or {})
    if mismatches:
        issues.append(_issue(
            "target_type_mismatch",
            "Existing table column types may not match the approved load schema.",
            severity="warning",
            columns=mismatches,
        ))
    return issues


def _live_columns(
    connection: DatabaseConnection,
    schema_name: str,
    target_table: str,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = :table
                    """
                ),
                {"schema": schema_name, "table": target_table},
            )
            return {str(row[0]): str(row[1]) for row in rows}, None
    except Exception as exc:
        return {}, _issue(
            "target_table_unreachable",
            "Could not inspect the selected target table before loading.",
            reason=str(exc)[:500],
        )
    finally:
        engine.dispose()


def _missing_schema_columns(columns: set[str], schema_json: dict[str, Any]) -> list[str]:
    missing = []
    for column in schema_json.get("target_columns", []):
        if not isinstance(column, dict):
            continue
        name = _safe_column(str(column.get("name") or ""))
        if name and name not in columns and name not in REQUIRED_SOURCE_COLUMNS:
            missing.append(name)
    return sorted(set(missing))


def _type_mismatches(live: dict[str, str], schema_json: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for column in schema_json.get("target_columns", []):
        if not isinstance(column, dict):
            continue
        name = _safe_column(str(column.get("name") or ""))
        expected = sql_type(str(column.get("type") or "text"))
        actual = live.get(name)
        if actual and not _compatible(expected, actual):
            rows.append({"column": name, "expected": expected, "actual": actual})
    return rows


def _compatible(expected: str, actual: str) -> bool:
    kind = actual.lower()
    if expected == "text":
        return True
    if expected in {"numeric", "integer", "double precision"}:
        return kind in {"numeric", "real", "double precision", "integer", "bigint", "smallint"}
    if expected == "date":
        return kind in {"date", "timestamp without time zone", "timestamp with time zone"}
    if expected == "timestamptz":
        return kind in {"date", "timestamp without time zone", "timestamp with time zone"}
    if expected == "boolean":
        return kind == "boolean"
    return True


def _safe_column(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")[:63]


def _issue(code: str, message: str, severity: str = "error", **extra: Any) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, **extra}
