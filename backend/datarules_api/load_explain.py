from typing import Any

from .config import get_settings
from .models import DatabaseConnection
from .row_review import normalize_row_status, row_is_loadable, row_review_counts
from .typed_values import validate_row_types


def attach_preview_explainability(rows: list[dict[str, Any]], schema_json: dict[str, Any]) -> list[dict[str, Any]]:
    typed_rows = [validate_row_types(row, schema_json) for row in rows]
    return [
        {**row, "row_status": normalize_row_status(row), "explainability": _row_explainability(row, schema_json)}
        for row in typed_rows
    ]


def build_agent_preparation_plan(
    connection: DatabaseConnection | None,
    schema_name: str,
    target_table: str,
    schema_json: dict[str, Any],
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = get_settings()
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    ready_rows = [row for row in rows if row_is_loadable(row)]
    return {
        "stage": "planned",
        "ready_for_agent": not errors and bool(ready_rows),
        "destination": {
            "connection_id": connection.id if connection else None,
            "connection_name": connection.name if connection else None,
            "schema_name": schema_name,
            "target_table": target_table,
            "target_mode": schema_json.get("target_mode"),
        },
        "structured_load": {
            "preview_rows": len(rows),
            "ready_rows": len(ready_rows),
            "blocked_rows": len(rows) - len(ready_rows),
            "row_review": row_review_counts(rows),
            "target_columns": [column.get("name") for column in schema_json.get("target_columns", [])],
            "source_references_required": True,
        },
        "retrieval": {
            "chunk_table": f"{target_table[:45]}_ai_chunks",
            "content_column": "content",
            "full_text_column": "search_tsv",
            "embedding_column": f"embedding vector({settings.embedding_dimensions})",
            "embedding_model": settings.embedding_model_id,
            "embedding_enabled": settings.enable_embedding_calls,
            "planned_indexes": ["GIN(search_tsv)", "HNSW(embedding vector_cosine_ops)", "BM25(id, content)"],
            "metadata": ["field_values", "extraction_source", "validation_errors"],
        },
        "quality": {
            "confidence": _confidence_summary(rows),
            "warnings": warnings,
            "blockers": errors,
        },
    }


def _row_explainability(row: dict[str, Any], schema_json: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("field_values") if isinstance(row.get("field_values"), dict) else {}
    sources = row.get("field_sources") if isinstance(row.get("field_sources"), dict) else {}
    columns = schema_json.get("target_columns", [])
    notes = [_field_note(column, fields, sources) for column in columns]
    missing_required = [note["field"] for note in notes if note["status"] == "required_missing"]
    confidence = float(row.get("confidence") or 0)
    status = "blocked" if row.get("validation_errors") or missing_required else _status(confidence)
    return {
        "status": status,
        "confidence_band": _band(confidence),
        "why_row_selected": _why_row(row),
        "source_reference": {
            "document_id": row.get("source_document_id"),
            "block_id": row.get("source_block_id"),
            "file": row.get("source_file"),
            "page": row.get("page"),
            "sheet": row.get("sheet"),
        },
        "field_coverage": {
            "filled": sum(1 for value in fields.values() if value not in (None, "")),
            "total": len(columns),
            "required_missing": missing_required,
        },
        "field_notes": notes,
    }


def _field_note(column: dict[str, Any], fields: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    name = str(column.get("name") or "")
    value = fields.get(name)
    required = bool(column.get("required"))
    if value not in (None, ""):
        status = "filled"
        reason = "Value extracted into preview field."
    elif required:
        status = "required_missing"
        reason = "Required target column has no extracted value."
    else:
        status = "missing"
        reason = "Optional field has no visible value in preview."
    return {"field": name, "status": status, "required": required, "reason": reason, "source": sources.get(name)}


def _why_row(row: dict[str, Any]) -> str:
    source = row.get("extraction_source") or "unknown extractor"
    file = row.get("source_file") or "source document"
    page = f", page {row.get('page')}" if row.get("page") else ""
    return f"Selected from {file}{page} by {source} with source block {row.get('source_block_id') or 'missing'}."


def _status(confidence: float) -> str:
    if confidence < 0.55:
        return "blocked"
    if confidence < 0.75:
        return "needs_review"
    return "ready"


def _band(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.7:
        return "medium"
    return "low"


def _confidence_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row.get("confidence") or 0) for row in rows]
    if not values:
        return {"average": 0, "low_rows": 0}
    return {
        "average": round(sum(values) / len(values), 3),
        "low_rows": sum(1 for value in values if value < 0.75),
    }
