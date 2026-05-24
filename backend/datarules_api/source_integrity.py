from typing import Any

from sqlalchemy.orm import Session

from .models import Document, DocumentBlock
from .row_identity import stable_row_id


def source_warnings_by_row(
    db: Session,
    dataset_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    return {
        stable_row_id(row): warnings
        for row in rows
        if (warnings := source_warnings(db, dataset_id, row))
    }


def source_reference_issues(
    db: Session,
    dataset_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings = source_warnings_by_row(db, dataset_id, rows)
    if not warnings:
        return []
    return [{
        "severity": "error",
        "code": "source_reference_invalid",
        "count": len(warnings),
        "message": f"{len(warnings)} preview row source reference(s) are invalid.",
        "rows": [
            {"row_id": row_id, "warnings": values}
            for row_id, values in list(warnings.items())[:20]
        ],
    }]


def source_warnings(db: Session, dataset_id: str, row: dict[str, Any]) -> list[str]:
    document_id = str(row.get("source_document_id") or "")
    block_id = str(row.get("source_block_id") or "")
    warnings: list[str] = []
    document = _document(db, dataset_id, document_id)
    block = _block(db, block_id)
    if not document_id:
        warnings.append("missing_source_document_id")
    elif not document:
        warnings.append("source_document_not_found")
    if not block_id:
        warnings.append("missing_source_block_id")
    elif not block:
        warnings.append("source_block_not_found")
    elif document_id and block.document_id != document_id:
        warnings.append("source_block_document_mismatch")
    return warnings


def _document(db: Session, dataset_id: str, document_id: str) -> Document | None:
    if not document_id:
        return None
    return db.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()


def _block(db: Session, block_id: str) -> DocumentBlock | None:
    return db.get(DocumentBlock, block_id) if block_id else None
