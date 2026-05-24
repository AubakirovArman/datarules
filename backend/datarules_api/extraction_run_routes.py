from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .ai_summaries import document_ai_summary
from .audit import record_audit_event
from .db import get_db
from .extraction_runs import (
    list_extraction_runs,
    load_run_snapshot,
    record_extraction_run,
    run_to_dict,
    snapshot_blocks,
    write_current_canonical,
)
from .extraction_run_diff import diff_extraction_runs
from .file_routes import _delete_answers_citing_document, _require_dataset, _require_mutable_files
from .load_plan_invalidation import invalidate_plans_for_repaired_document
from .materialized_cleanup import purge_document_materialization
from .models import Document, DocumentAiSummary, DocumentBlock, DocumentExtractionRun, DocumentReview
from .routing import create_document_review

router = APIRouter()


@router.get("/datasets/{dataset_id}/files/{document_id}/extraction-runs")
def get_extraction_runs(dataset_id: str, document_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    _document(db, dataset_id, document_id)
    return {"runs": list_extraction_runs(db, dataset_id, document_id)}


@router.get("/datasets/{dataset_id}/files/{document_id}/extraction-runs/{run_id}/diff")
def get_extraction_run_diff(
    dataset_id: str,
    document_id: str,
    run_id: str,
    against_run_id: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _document(db, dataset_id, document_id)
    left = _run(db, dataset_id, document_id, run_id)
    right = _comparison_run(db, dataset_id, document_id, run_id, against_run_id)
    try:
        return diff_extraction_runs(left, right)
    except FileNotFoundError as exc:
        raise HTTPException(409, "Extraction run snapshot is missing") from exc


@router.post("/datasets/{dataset_id}/files/{document_id}/extraction-runs/{run_id}/rollback")
def rollback_extraction_run(
    dataset_id: str,
    document_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    document = _document(db, dataset_id, document_id)
    _require_mutable_files(db, dataset_id)
    run = _run(db, dataset_id, document_id, run_id)
    try:
        snapshot = load_run_snapshot(run)
    except FileNotFoundError as exc:
        raise HTTPException(409, "Extraction run snapshot is missing") from exc

    blocks = snapshot_blocks(document.id, snapshot)
    _replace_document_state(db, document, blocks, snapshot)
    canonical = _rollback_canonical(snapshot, document, run)
    write_current_canonical(document.id, canonical)
    ai_summary = document_ai_summary(db, document, blocks)
    create_document_review(db, document, blocks, ai_summary)
    new_run = record_extraction_run(db, document, blocks, canonical, "rollback", document.status)
    removed_answers = _delete_answers_citing_document(db, dataset_id, document.id)
    materialized = purge_document_materialization(db, document.id)
    invalidated = invalidate_plans_for_repaired_document(db, dataset_id, document.id, document.file_name)
    record_audit_event(
        db,
        "document.extraction_rolled_back",
        "document",
        document.id,
        dataset_id,
        {
            "restored_run_id": run.id,
            "new_run_id": new_run.id,
            "removed_answers": removed_answers,
            "materialized_cleanup": materialized,
            "invalidated_load_plans": invalidated,
        },
    )
    db.commit()
    return {
        "status": "rolled_back",
        "document_id": document.id,
        "restored_run": run_to_dict(run),
        "new_run": run_to_dict(new_run),
        "removed_answers": removed_answers,
        "materialized_cleanup": materialized,
        "invalidated_load_plans": invalidated,
    }


def _document(db: Session, dataset_id: str, document_id: str) -> Document:
    _require_dataset(db, dataset_id)
    document = db.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    return document


def _run(db: Session, dataset_id: str, document_id: str, run_id: str) -> DocumentExtractionRun:
    run = (
        db.query(DocumentExtractionRun)
        .filter(DocumentExtractionRun.id == run_id)
        .filter(DocumentExtractionRun.dataset_id == dataset_id)
        .filter(DocumentExtractionRun.document_id == document_id)
        .first()
    )
    if not run:
        raise HTTPException(404, "Extraction run not found")
    return run


def _comparison_run(
    db: Session,
    dataset_id: str,
    document_id: str,
    run_id: str,
    against_run_id: str | None,
) -> DocumentExtractionRun:
    if against_run_id:
        return _run(db, dataset_id, document_id, against_run_id)
    rows = (
        db.query(DocumentExtractionRun)
        .filter(DocumentExtractionRun.dataset_id == dataset_id)
        .filter(DocumentExtractionRun.document_id == document_id)
        .order_by(DocumentExtractionRun.created_at.desc())
        .all()
    )
    for row in rows:
        if row.id != run_id:
            return row
    raise HTTPException(409, "Another extraction run is required for diff")


def _replace_document_state(
    db: Session,
    document: Document,
    blocks: list[DocumentBlock],
    snapshot: dict[str, Any],
) -> None:
    db.query(DocumentReview).filter(DocumentReview.document_id == document.id).delete()
    db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document.id).delete()
    db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).delete()
    document.status = str(snapshot.get("document_status") or _status_from_blocks(blocks))
    for block in blocks:
        db.add(block)
    db.flush()


def _rollback_canonical(
    snapshot: dict[str, Any],
    document: Document,
    run: DocumentExtractionRun,
) -> dict[str, Any]:
    canonical = dict(snapshot)
    canonical["document_id"] = document.id
    canonical["file_name"] = document.file_name
    canonical["document_status"] = document.status
    canonical["run_type"] = "rollback"
    canonical["restored_from_run_id"] = run.id
    return canonical


def _status_from_blocks(blocks: list[DocumentBlock]) -> str:
    return "needs_review" if any(block.block_type == "error" for block in blocks) else "extracted"
