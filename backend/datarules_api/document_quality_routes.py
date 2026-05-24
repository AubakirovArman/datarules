from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .document_quality import build_quality_profile, quality_action_keys, quality_load_issues
from .models import Dataset, Document, DocumentBlock, DocumentReview

router = APIRouter()


@router.get("/datasets/{dataset_id}/document-quality")
def document_quality_report(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found")
    documents = db.query(Document).filter(Document.dataset_id == dataset_id).order_by(Document.created_at).all()
    blocks = _blocks_by_doc(db, [document.id for document in documents])
    reviews = {row.document_id: row for row in db.query(DocumentReview).filter(DocumentReview.dataset_id == dataset_id).all()}
    rows = [_document_row(document, blocks[document.id], reviews.get(document.id)) for document in documents]
    return {
        "dataset_id": dataset_id,
        "status": _status(rows),
        "counts": _counts(rows),
        "documents": rows,
        "actions": _actions(rows),
    }


def _blocks_by_doc(db: Session, ids: list[str]) -> dict[str, list[DocumentBlock]]:
    grouped: dict[str, list[DocumentBlock]] = defaultdict(list)
    if not ids:
        return grouped
    for block in db.query(DocumentBlock).filter(DocumentBlock.document_id.in_(ids)).order_by(DocumentBlock.page).all():
        grouped[block.document_id].append(block)
    return grouped


def _document_row(document: Document, blocks: list[DocumentBlock], review: DocumentReview | None) -> dict[str, Any]:
    quality = build_quality_profile(blocks)
    issues = quality_load_issues(document.id, document.file_name, quality)
    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "document_status": document.status,
        "route_status": review.status if review else "missing",
        "selected_table": review.selected_table if review else None,
        "quality": quality,
        "load_gate": "blocked" if any(item["severity"] == "error" for item in issues) else "warning" if issues else "passed",
        "issues": issues,
        "actions": quality_action_keys(quality),
    }


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "documents": len(rows),
        "ready": sum(1 for row in rows if row["quality"]["status"] == "ready"),
        "needs_review": sum(1 for row in rows if row["quality"]["status"] == "needs_review"),
        "blocked": sum(1 for row in rows if row["quality"]["status"] == "blocked"),
        "low_confidence_blocks": sum(int(row["quality"]["low_confidence_blocks"]) for row in rows),
        "image_pages_pending": sum(int(row["quality"]["image_pages_pending"]) for row in rows),
    }


def _status(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "pending"
    gates = {row["load_gate"] for row in rows}
    if "blocked" in gates:
        return "blocked"
    if "warning" in gates:
        return "needs_review"
    return "ready"


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["upload_documents"]
    actions = []
    for row in rows:
        actions.extend(row["actions"])
    return sorted(set(actions))[:8]
