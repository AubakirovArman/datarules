from typing import Any

from .row_identity import stable_row_id
from .row_review import normalize_row_status, row_is_loadable


def diff_load_preview(
    current_rows: list[dict[str, Any]],
    fresh_rows: list[dict[str, Any]],
    current_issues: list[dict[str, Any]],
    fresh_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    current = {_row_key(row): row for row in current_rows}
    fresh = {_row_key(row): row for row in fresh_rows}
    added = [_row_note(fresh[key], "added") for key in sorted(fresh.keys() - current.keys())]
    removed = [_row_note(current[key], "removed") for key in sorted(current.keys() - fresh.keys())]
    changed = [
        _row_change(current[key], fresh[key])
        for key in sorted(current.keys() & fresh.keys())
        if _row_fingerprint(current[key]) != _row_fingerprint(fresh[key])
    ]
    return {
        "summary": {
            "current_rows": len(current_rows),
            "fresh_rows": len(fresh_rows),
            "added_rows": len(added),
            "removed_rows": len(removed),
            "changed_rows": len(changed),
            "current_loadable": sum(1 for row in current_rows if row_is_loadable(row)),
            "fresh_loadable": sum(1 for row in fresh_rows if row_is_loadable(row)),
            "current_errors": _issue_count(current_issues, "error"),
            "fresh_errors": _issue_count(fresh_issues, "error"),
        },
        "added_rows": added[:20],
        "removed_rows": removed[:20],
        "changed_rows": changed[:30],
        "issue_delta": _issue_delta(current_issues, fresh_issues),
    }


def _row_key(row: dict[str, Any]) -> str:
    return stable_row_id(row)


def _row_fingerprint(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("source_document_id"),
        row.get("source_block_id"),
        row.get("content"),
        row.get("field_values"),
        tuple(row.get("validation_errors") or []),
        normalize_row_status(row),
        round(float(row.get("confidence") or 0), 4),
    )


def _row_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": _row_key(after),
        "source_file": after.get("source_file") or before.get("source_file"),
        "before_status": normalize_row_status(before),
        "after_status": normalize_row_status(after),
        "before_source_block_id": before.get("source_block_id"),
        "after_source_block_id": after.get("source_block_id"),
        "source_changed": before.get("source_block_id") != after.get("source_block_id"),
        "before_confidence": before.get("confidence"),
        "after_confidence": after.get("confidence"),
        "content_delta": len(str(after.get("content") or "")) - len(str(before.get("content") or "")),
        "field_changes": _field_changes(before.get("field_values"), after.get("field_values")),
        "before_errors": before.get("validation_errors") or [],
        "after_errors": after.get("validation_errors") or [],
        "before_content": _clip(str(before.get("content") or "")),
        "after_content": _clip(str(after.get("content") or "")),
    }


def _row_note(row: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "row_id": _row_key(row),
        "status": status,
        "source_file": row.get("source_file"),
        "row_status": normalize_row_status(row),
        "confidence": row.get("confidence"),
        "content": _clip(str(row.get("content") or "")),
        "field_values": row.get("field_values") or {},
    }


def _field_changes(before_value: Any, after_value: Any) -> list[dict[str, Any]]:
    before = before_value if isinstance(before_value, dict) else {}
    after = after_value if isinstance(after_value, dict) else {}
    changes = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes.append({"field": key, "before": before.get(key), "after": after.get(key)})
    return changes[:20]


def _issue_delta(current_issues: list[dict[str, Any]], fresh_issues: list[dict[str, Any]]) -> dict[str, Any]:
    current = {_issue_key(issue): issue for issue in current_issues}
    fresh = {_issue_key(issue): issue for issue in fresh_issues}
    return {
        "added": [fresh[key] for key in sorted(fresh.keys() - current.keys())][:20],
        "resolved": [current[key] for key in sorted(current.keys() - fresh.keys())][:20],
        "same_count": len(current.keys() & fresh.keys()),
    }


def _issue_key(issue: dict[str, Any]) -> str:
    return "|".join(str(issue.get(key) or "") for key in ("severity", "code", "document_id", "message"))


def _issue_count(issues: list[dict[str, Any]], severity: str) -> int:
    return sum(1 for issue in issues if issue.get("severity") == severity)


def _clip(value: str, limit: int = 360) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
