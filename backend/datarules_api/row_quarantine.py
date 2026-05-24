from collections import Counter
from typing import Any

from .row_identity import stable_row_id
from .row_review import normalize_row_status, row_is_loadable


def quarantine_report(
    rows: list[dict[str, Any]],
    source_warnings: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    source_warnings = source_warnings or {}
    quarantined = [
        _quarantine_row(row, source_warnings.get(stable_row_id(row), []))
        for row in rows
        if not row_is_loadable(row) or source_warnings.get(stable_row_id(row))
    ]
    reasons = Counter(reason for row in quarantined for reason in row["reasons"])
    statuses = Counter(row["row_status"] for row in quarantined)
    return {
        "summary": {
            "total_rows": len(rows),
            "loadable_rows": sum(1 for row in rows if row_is_loadable(row)),
            "quarantined_rows": len(quarantined),
            "by_reason": dict(sorted(reasons.items())),
            "by_status": dict(sorted(statuses.items())),
        },
        "rows": quarantined[:100],
    }


def _quarantine_row(row: dict[str, Any], source_warnings: list[str]) -> dict[str, Any]:
    return {
        "row_id": stable_row_id(row),
        "source_document_id": row.get("source_document_id"),
        "source_block_id": row.get("source_block_id"),
        "source_file": row.get("source_file"),
        "page": row.get("page"),
        "sheet": row.get("sheet"),
        "row_status": normalize_row_status(row),
        "confidence": row.get("confidence"),
        "reasons": _reasons(row, source_warnings),
        "validation_errors": row.get("validation_errors") or [],
        "field_values": row.get("field_values") or {},
        "content": _clip(str(row.get("content") or row.get("field_text") or "")),
    }


def _reasons(row: dict[str, Any], source_warnings: list[str]) -> list[str]:
    reasons = [f"source:{item}" for item in source_warnings]
    status = normalize_row_status(row)
    if status in {"needs_review", "rejected"}:
        reasons.append(status)
    if row.get("validation_errors"):
        reasons.extend(f"validation:{item}" for item in row.get("validation_errors") or [])
    try:
        if float(row.get("confidence") or 0) < 0.75:
            reasons.append("low_confidence")
    except (TypeError, ValueError):
        reasons.append("invalid_confidence")
    if not row.get("source_document_id"):
        reasons.append("missing_source_document_id")
    if not row.get("source_block_id"):
        reasons.append("missing_source_block_id")
    return sorted(set(reasons or ["not_loadable"]))


def _clip(value: str, limit: int = 420) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
