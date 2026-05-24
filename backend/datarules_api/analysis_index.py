from typing import Any

from sqlalchemy.orm import Session

from .models import Document, DocumentBlock, LoadPlan
from .parsers.common import clean_text


def analysis_index_rows(db: Session, plan: LoadPlan) -> list[dict[str, Any]]:
    documents = {document.id: document for document in _documents(db, plan)}
    if not documents:
        return []
    blocks = (
        db.query(DocumentBlock)
        .filter(DocumentBlock.document_id.in_(documents))
        .order_by(DocumentBlock.document_id, DocumentBlock.page, DocumentBlock.id)
        .all()
    )
    return [_row(documents[block.document_id], block) for block in blocks if clean_text(block.text or "")]


def _documents(db: Session, plan: LoadPlan) -> list[Document]:
    query = db.query(Document).filter(Document.dataset_id == plan.dataset_id)
    document_ids = _document_ids(plan)
    if document_ids:
        query = query.filter(Document.id.in_(document_ids))
    return query.order_by(Document.created_at).all()


def _document_ids(plan: LoadPlan) -> list[str]:
    scope = (plan.schema_json or {}).get("document_scope")
    scoped = scope.get("document_ids") if isinstance(scope, dict) else None
    if isinstance(scoped, list) and scoped:
        return [str(item) for item in scoped if item]
    ids = [row.get("source_document_id") for row in plan.preview_rows or [] if isinstance(row, dict)]
    return sorted({str(item) for item in ids if item})


def _row(document: Document, block: DocumentBlock) -> dict[str, Any]:
    return {
        "row_id": f"analysis:{block.id}",
        "source_document_id": document.id,
        "source_file": document.file_name,
        "source_block_id": block.id,
        "page": block.page,
        "sheet": block.sheet_name,
        "content": clean_text(block.text or "")[:3000],
        "field_text": clean_text(block.text or "")[:1200],
        "field_values": {},
        "field_sources": {},
        "confidence": block.confidence,
        "extraction_source": "analysis_only_block_index",
        "row_status": "approved",
        "validation_errors": [],
    }
