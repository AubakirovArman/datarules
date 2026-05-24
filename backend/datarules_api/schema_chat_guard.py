import re
from typing import Any

from .db_identifiers import MANAGED_COLUMNS, identifier_issues


def sanitize_schema_proposal(value: dict[str, Any]) -> dict[str, Any]:
    proposal = dict(value or {})
    warnings: list[dict[str, str]] = []
    proposal["table_name"] = _safe_identifier(str(proposal.get("table_name") or ""), "custom_records", warnings, "table_name")
    columns = _safe_columns(proposal.get("columns"), warnings)
    proposal["columns"] = columns
    schema_json = {"target_columns": columns}
    residual = identifier_issues("public", proposal["table_name"], schema_json)
    proposal["identifier_warnings"] = [*proposal.get("identifier_warnings", []), *warnings, *residual]
    proposal["schema_json"] = {
        "description": str(proposal.get("assistant_message") or proposal.get("description") or ""),
        "target_columns": columns,
        "source_references_required": True,
    }
    return proposal


def _safe_columns(value: Any, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        original = str(item.get("name") or "")
        name = _safe_identifier(original, "", warnings, "column")
        if not name:
            continue
        if name in MANAGED_COLUMNS:
            warnings.append({"code": "managed_column_removed", "field": original, "safe_name": name})
            continue
        if name in seen:
            warnings.append({"code": "duplicate_column_removed", "field": original, "safe_name": name})
            continue
        seen.add(name)
        rows.append({"name": name, "type": str(item.get("type") or "text"), "required": bool(item.get("required"))})
    return rows or [
        {"name": "title", "type": "text", "required": False},
        {"name": "summary", "type": "text", "required": False},
    ]


def _safe_identifier(value: str, fallback: str, warnings: list[dict[str, str]], field: str) -> str:
    original = value.strip()
    safe = re.sub(r"[^a-z0-9_]+", "_", original.lower()).strip("_")
    if safe and safe[0].isdigit():
        safe = f"{field[:1]}_{safe}"
    safe = safe[:63].strip("_") or fallback
    if original and safe != original:
        warnings.append({"code": "identifier_normalized", "field": original, "safe_name": safe})
    return safe
