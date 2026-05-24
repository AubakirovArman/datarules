from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .config import get_settings
from .db import get_db
from .file_routes import _delete_answers_citing_document, _require_mutable_files, _remove_dir, _require_dataset
from .jobs import _process_document
from .load_plan_invalidation import invalidate_plans_for_repaired_document
from .materialized_cleanup import purge_document_materialization
from .models import Document, DocumentAiSummary, DocumentReview

router = APIRouter()


@router.post("/datasets/{dataset_id}/files/{document_id}/repair-extraction")
def repair_document_extraction(dataset_id: str, document_id: str, db: Session = Depends(get_db)) -> dict:
    _require_dataset(db, dataset_id)
    _require_mutable_files(db, dataset_id)
    document = db.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    _clear_cached_document_state(db, document)
    _remove_dir(get_settings().page_image_dir / document.id)
    _process_document(db, document, [], run_type="repair")
    removed_answers = _delete_answers_citing_document(db, dataset_id, document.id)
    materialized = purge_document_materialization(db, document.id)
    invalidated = invalidate_plans_for_repaired_document(db, dataset_id, document.id, document.file_name)
    record_audit_event(
        db,
        "document.repaired",
        "document",
        document.id,
        dataset_id,
        {
            "file_name": document.file_name,
            "removed_answers": removed_answers,
            "materialized_cleanup": materialized,
            "invalidated_load_plans": invalidated,
        },
    )
    db.commit()
    db.refresh(document)
    return {
        "status": "repaired",
        "document_id": document.id,
        "document_status": document.status,
        "canonical_path": str(get_settings().canonical_storage_dir / f"{document.id}.json"),
        "removed_answers": removed_answers,
        "materialized_cleanup": materialized,
        "invalidated_load_plans": invalidated,
    }


def _clear_cached_document_state(db: Session, document: Document) -> None:
    db.query(DocumentReview).filter(DocumentReview.document_id == document.id).delete()
    db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document.id).delete()
    canonical = get_settings().canonical_storage_dir / f"{document.id}.json"
    try:
        Path(canonical).unlink(missing_ok=True)
    except OSError:
        pass
    db.commit()
