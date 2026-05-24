from typing import Any

from .parsers.common import clean_json, clean_text


def build_field_sources(
    document: Any,
    fields: dict[str, Any],
    source_block: Any,
    provided: Any,
    confidence: float,
    extraction_source: str | None,
) -> dict[str, dict[str, Any]]:
    refs = provided if isinstance(provided, dict) else {}
    return {
        field: _source(document, source_block, refs.get(field), confidence, extraction_source)
        for field, value in fields.items()
        if value not in (None, "")
    }


def normalize_field_sources(row: dict[str, Any], fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs = row.get("field_sources") if isinstance(row.get("field_sources"), dict) else {}
    source = _row_source(row)
    return {
        field: _merge_source(source, refs.get(field))
        for field, value in fields.items()
        if value not in (None, "")
    }


def _source(
    document: Any,
    block: Any,
    provided: Any,
    confidence: float,
    extraction_source: str | None,
) -> dict[str, Any]:
    base = {
        "document_id": getattr(document, "id", None),
        "block_id": getattr(block, "id", None),
        "file": getattr(document, "file_name", None),
        "page": getattr(block, "page", None),
        "sheet": getattr(block, "sheet_name", None),
        "confidence": confidence,
        "evidence": clean_text(str(getattr(block, "text", "") or ""))[:320],
        "extraction_source": extraction_source or "unknown",
    }
    return _merge_source(base, provided)


def _row_source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row.get("source_document_id"),
        "block_id": row.get("source_block_id"),
        "file": row.get("source_file"),
        "page": row.get("page"),
        "sheet": row.get("sheet"),
        "confidence": row.get("confidence"),
        "evidence": clean_text(str(row.get("content") or row.get("field_text") or ""))[:320],
        "extraction_source": row.get("extraction_source") or "manual_preview",
    }


def _merge_source(base: dict[str, Any], provided: Any) -> dict[str, Any]:
    ref = provided if isinstance(provided, dict) else {}
    merged = {**base, **{key: value for key, value in ref.items() if value not in (None, "")}}
    return clean_json(merged)
