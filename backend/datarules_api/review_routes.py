from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .db import get_db
from .load_plan_invalidation import invalidate_plans_for_routing_change
from .models import Dataset, Document, DocumentReview
from .routing import refresh_document_reviews
from .schemas import DocumentReviewOut

router = APIRouter()


@router.post("/datasets/{dataset_id}/document-reviews/accept-recommended", response_model=list[DocumentReviewOut])
def accept_recommended_reviews(dataset_id: str, db: Session = Depends(get_db)) -> list[DocumentReviewOut]:
    _require_dataset(db, dataset_id)
    refresh_document_reviews(db, dataset_id)
    reviews = db.query(DocumentReview).filter(DocumentReview.dataset_id == dataset_id).all()
    changed_ids: list[str] = []
    skipped_ids: list[str] = []
    invalidated: list[dict] = []
    for review in reviews:
        if review.status == "confirmed":
            continue
        doc_type = review.selected_doc_type or _first_value(review.doc_type_options)
        table = review.selected_table or _first_value(review.table_options)
        if not doc_type or not table:
            skipped_ids.append(review.id)
            continue
        review.selected_doc_type = doc_type
        review.selected_table = table
        review.notes = review.notes or "Accepted from DataRules recommendation"
        review.status = "confirmed"
        review.updated_at = datetime.utcnow()
        changed_ids.append(review.id)
        invalidated.extend(invalidate_plans_for_routing_change(db, dataset_id, review.document_id))
    record_audit_event(
        db,
        "document_review.accept_recommended",
        "dataset",
        dataset_id,
        dataset_id,
        {"confirmed": len(changed_ids), "skipped": skipped_ids, "invalidated_load_plans": invalidated},
    )
    db.commit()
    return _review_outputs(db, dataset_id)


def _first_value(options: list[dict]) -> str:
    if not options:
        return ""
    return str(options[0].get("value") or "")


def _review_outputs(db: Session, dataset_id: str) -> list[DocumentReviewOut]:
    rows = (
        db.query(DocumentReview, Document)
        .join(Document, Document.id == DocumentReview.document_id)
        .filter(DocumentReview.dataset_id == dataset_id)
        .order_by(DocumentReview.created_at.desc())
        .all()
    )
    return [
        DocumentReviewOut.model_validate(review).model_copy(update={"file_name": document.file_name})
        for review, document in rows
    ]


def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset
