import re
from typing import Any

IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
MANAGED_COLUMNS = {
    "id",
    "content",
    "source_document_id",
    "source_block_id",
    "source_file",
    "page",
    "sheet",
    "confidence",
    "field_values",
    "field_sources",
    "metadata",
    "created_at",
}


def identifier_issues(schema_name: str, table_name: str, schema_json: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    issues.extend(_identifier_issue("schema_name", schema_name, "invalid_schema_identifier"))
    issues.extend(_identifier_issue("target_table", table_name, "invalid_table_identifier"))
    issues.extend(_column_issues(schema_json))
    return issues


def first_identifier_error(schema_name: str, table_name: str, schema_json: dict[str, Any]) -> str | None:
    issues = identifier_issues(schema_name, table_name, schema_json)
    if not issues:
        return None
    return "; ".join(str(issue["message"]) for issue in issues[:4])


def _column_issues(schema_json: dict[str, Any]) -> list[dict[str, Any]]:
    columns = schema_json.get("target_columns") if isinstance(schema_json, dict) else []
    if not isinstance(columns, list):
        return []
    issues = []
    seen: set[str] = set()
    for column in columns:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "").strip()
        if name in seen:
            issues.append(_issue("duplicate_target_column", "target_columns", name, f"Duplicate target column '{name}'."))
        seen.add(name)
        if name in MANAGED_COLUMNS:
            issues.append(_issue("reserved_target_column", "target_columns", name, f"Column '{name}' is managed by DataRules."))
        issues.extend(_identifier_issue("target_columns", name, "invalid_column_identifier"))
    return issues


def _identifier_issue(field: str, value: str, code: str) -> list[dict[str, Any]]:
    clean = str(value or "").strip()
    if IDENTIFIER_RE.fullmatch(clean):
        return []
    return [_issue(code, field, clean, f"{field} must be snake_case, start with a letter or _, and be <= 63 chars.")]


def _issue(code: str, field: str, value: str, message: str) -> dict[str, Any]:
    return {"severity": "error", "code": code, "field": field, "value": value, "message": message}
