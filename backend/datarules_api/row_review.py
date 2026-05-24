from typing import Any

APPROVED = "approved"
CANDIDATE = "candidate"
NEEDS_REVIEW = "needs_review"
REJECTED = "rejected"
STATUSES = {APPROVED, CANDIDATE, NEEDS_REVIEW, REJECTED}


def normalize_row_status(row: dict[str, Any]) -> str:
    status = str(row.get("row_status") or "").strip().lower()
    if status in STATUSES:
        return status
    if row.get("validation_errors"):
        return NEEDS_REVIEW
    try:
        confidence = float(row.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    return NEEDS_REVIEW if confidence < 0.75 else CANDIDATE


def row_is_loadable(row: dict[str, Any]) -> bool:
    return normalize_row_status(row) in {APPROVED, CANDIDATE} and not row.get("validation_errors")


def row_review_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(STATUSES)}
    for row in rows:
        counts[normalize_row_status(row)] += 1
    counts["loadable"] = sum(1 for row in rows if row_is_loadable(row))
    counts["blocked"] = len(rows) - counts["loadable"]
    return counts
