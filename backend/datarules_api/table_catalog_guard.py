from typing import Any

from .db_identifiers import IDENTIFIER_RE, MANAGED_COLUMNS, identifier_issues


def table_catalog_error(schema_name: str, table_name: str, columns: list[dict[str, Any]]) -> str | None:
    issues = identifier_issues(schema_name, table_name, {})
    issues.extend(_column_issues(columns))
    if not issues:
        return None
    return "; ".join(str(issue["message"]) for issue in issues[:4])


def _column_issues(columns: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues = []
    seen: set[str] = set()
    for column in columns:
        name = str(column.get("name") or "").strip()
        if not name or name in MANAGED_COLUMNS:
            continue
        if name in seen:
            issues.append({"code": "duplicate_catalog_column", "message": f"Duplicate catalog column '{name}'."})
        seen.add(name)
        if not IDENTIFIER_RE.fullmatch(name):
            issues.append({
                "code": "invalid_catalog_column",
                "message": "Catalog column names must be snake_case and <= 63 chars.",
            })
    return issues
