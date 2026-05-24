from typing import Any

from .parsers.common import clean_text


def stable_row_id(row: dict[str, Any]) -> str:
    explicit = clean_text(str(row.get("row_id") or ""))
    if explicit:
        return explicit
    document_id = clean_text(str(row.get("source_document_id") or "missing_document"))
    block_id = clean_text(str(row.get("source_block_id") or "missing_block"))
    return f"{document_id}:{block_id}"
