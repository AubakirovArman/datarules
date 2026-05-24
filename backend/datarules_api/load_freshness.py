import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from .models import Document, DocumentAiSummary, DocumentBlock, DocumentReview, LoadPlan
from .parsers.common import clean_json

SNAPSHOT_KEY = "source_snapshot"


def attach_source_snapshot(
    db: Session,
    dataset_id: str,
    schema_json: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    schema = dict(schema_json or {})
    schema[SNAPSHOT_KEY] = build_source_snapshot(db, dataset_id, schema, rows)
    return schema


def stale_preview_issue(db: Session, plan: LoadPlan) -> dict[str, Any] | None:
    expected = (plan.schema_json or {}).get(SNAPSHOT_KEY)
    if not isinstance(expected, dict) or not expected.get("fingerprint"):
        return None
    current = build_source_snapshot(db, plan.dataset_id, plan.schema_json or {}, plan.preview_rows or [])
    if current.get("fingerprint") == expected.get("fingerprint"):
        return None
    return {
        "severity": "error",
        "code": "stale_preview",
        "message": "Documents or routing changed after this preview was created. Rebuild preview before loading.",
        "expected_fingerprint": expected.get("fingerprint"),
        "current_fingerprint": current.get("fingerprint"),
    }


def merge_stale_issue(issues: list[dict[str, Any]], issue: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [item for item in issues if item.get("code") != "stale_preview"]
    rows.append(issue)
    return rows


def build_source_snapshot(
    db: Session,
    dataset_id: str,
    schema_json: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    document_ids = _document_ids(db, dataset_id, schema_json, rows)
    documents = [_document_snapshot(db, document) for document in _documents(db, dataset_id, document_ids)]
    payload = {"version": 1, "document_ids": document_ids, "documents": documents}
    return {**payload, "fingerprint": _hash(payload)}


def _document_ids(
    db: Session,
    dataset_id: str,
    schema_json: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[str]:
    scope = (schema_json or {}).get("document_scope") if isinstance(schema_json, dict) else None
    scoped = scope.get("document_ids") if isinstance(scope, dict) else None
    ids = scoped if isinstance(scoped, list) else []
    if not ids:
        ids = [row.get("source_document_id") for row in rows if isinstance(row, dict)]
    if not ids:
        ids = [row[0] for row in db.query(Document.id).filter(Document.dataset_id == dataset_id).all()]
    return sorted({str(item) for item in ids if item})


def _documents(db: Session, dataset_id: str, document_ids: list[str]) -> list[Document]:
    if not document_ids:
        return []
    return (
        db.query(Document)
        .filter(Document.dataset_id == dataset_id)
        .filter(Document.id.in_(document_ids))
        .order_by(Document.id)
        .all()
    )


def _document_snapshot(db: Session, document: Document) -> dict[str, Any]:
    review = db.query(DocumentReview).filter(DocumentReview.document_id == document.id).first()
    summary = (
        db.query(DocumentAiSummary)
        .filter(DocumentAiSummary.document_id == document.id)
        .order_by(DocumentAiSummary.updated_at.desc())
        .first()
    )
    return {
        "id": document.id,
        "sha256": document.sha256,
        "status": document.status,
        "blocks_hash": _blocks_hash(db, document.id),
        "review_status": review.status if review else None,
        "review_table": review.selected_table if review else None,
        "review_updated_at": review.updated_at.isoformat() if review else None,
        "summary_updated_at": summary.updated_at.isoformat() if summary else None,
    }


def _blocks_hash(db: Session, document_id: str) -> str:
    blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).order_by(DocumentBlock.id).all()
    payload = [
        {
            "id": block.id,
            "type": block.block_type,
            "page": block.page,
            "sheet": block.sheet_name,
            "text": block.text,
            "table_json": block.table_json,
            "confidence": block.confidence,
        }
        for block in blocks
    ]
    return _hash(payload)


def _hash(value: Any) -> str:
    data = json.dumps(clean_json(value), ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(data).hexdigest()
