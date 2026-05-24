from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .config import get_settings
from .db import get_db
from .ingestion_state import active_ingestion_job
from .load_plan_invalidation import invalidate_plans_for_deleted_document
from .materialized_cleanup import purge_document_materialization
from .models import AgentAnswer, Document, DocumentAiSummary, DocumentBlock, DocumentExtractionRun, DocumentReview
from .schemas import DocumentOut
from .storage import UploadPolicyError, save_upload

router = APIRouter()


@router.post("/datasets/{dataset_id}/files", response_model=list[DocumentOut])
async def upload_files(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    files: Annotated[list[UploadFile], File()],
) -> list[Document]:
    _require_dataset(db, dataset_id)
    _require_mutable_files(db, dataset_id)
    documents: list[Document] = []
    saved_paths: list[Path] = []
    try:
        for upload in files:
            path, digest = await save_upload(dataset_id, upload)
            saved_paths.append(path)
            existing = _existing_document(db, dataset_id, digest, documents)
            if existing:
                _unlink(path)
                record_audit_event(db, "document_upload.duplicate", "document", existing.id, dataset_id, _upload_payload(upload, digest))
                documents.append(existing)
                continue
            document = Document(
                dataset_id=dataset_id,
                file_name=upload.filename or path.name,
                file_type=upload.content_type or "application/octet-stream",
                storage_path=str(path),
                sha256=digest,
            )
            db.add(document)
            db.flush()
            documents.append(document)
            record_audit_event(db, "document.uploaded", "document", document.id, dataset_id, _upload_payload(upload, digest))
        db.commit()
    except UploadPolicyError as exc:
        db.rollback()
        for path in saved_paths:
            _unlink(path)
        record_audit_event(db, "document_upload.rejected", "dataset", dataset_id, dataset_id, {"code": exc.code, "message": str(exc)})
        db.commit()
        raise HTTPException(400, str(exc)) from exc
    for document in documents:
        db.refresh(document)
    return documents


@router.get("/datasets/{dataset_id}/files", response_model=list[DocumentOut])
def list_files(dataset_id: str, db: Session = Depends(get_db)) -> list[Document]:
    _require_dataset(db, dataset_id)
    return db.query(Document).filter(Document.dataset_id == dataset_id).all()


@router.get("/datasets/{dataset_id}/files/{document_id}/canonical")
def canonical_document(dataset_id: str, document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.dataset_id == dataset_id)
        .first()
    )
    if not document:
        raise HTTPException(404, "Document not found")
    path = get_settings().canonical_storage_dir / f"{document.id}.json"
    if not path.exists():
        raise HTTPException(404, "Canonical document is not ready")
    filename = f"{Path(document.file_name).stem or document.id}.canonical.json"
    return FileResponse(path, media_type="application/json", filename=filename)


@router.delete("/datasets/{dataset_id}/files/{document_id}")
def delete_file(dataset_id: str, document_id: str, db: Session = Depends(get_db)) -> dict:
    _require_mutable_files(db, dataset_id)
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.dataset_id == dataset_id)
        .first()
    )
    if not document:
        raise HTTPException(404, "Document not found")

    raw_path = Path(document.storage_path)
    canonical_path = get_settings().canonical_storage_dir / f"{document.id}.json"
    runs_dir = get_settings().canonical_storage_dir / "runs" / document.id
    image_dir = get_settings().page_image_dir / document.id

    removed_answers = _delete_answers_citing_document(db, dataset_id, document.id)
    materialized = purge_document_materialization(db, document.id)
    invalidated = invalidate_plans_for_deleted_document(db, dataset_id, document.id, document.file_name)
    record_audit_event(
        db,
        "document.deleted",
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
    db.query(DocumentReview).filter(DocumentReview.document_id == document.id).delete()
    db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document.id).delete()
    db.query(DocumentExtractionRun).filter(DocumentExtractionRun.document_id == document.id).delete()
    db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).delete()
    db.delete(document)
    db.commit()

    _unlink(raw_path)
    _unlink(canonical_path)
    _remove_dir(runs_dir)
    _remove_dir(image_dir)
    return {
        "status": "deleted",
        "document_id": document_id,
        "removed_answers": removed_answers,
        "materialized_cleanup": materialized,
        "invalidated_load_plans": invalidated,
    }


def _require_dataset(db: Session, dataset_id: str) -> None:
    if not db.query(Document.id).filter(Document.dataset_id == dataset_id).first():
        # Dataset lookup is intentionally local to avoid importing main helpers.
        from .models import Dataset

        if not db.get(Dataset, dataset_id):
            raise HTTPException(404, "Dataset not found")


def _require_mutable_files(db: Session, dataset_id: str) -> None:
    active = active_ingestion_job(db, dataset_id)
    if active:
        raise HTTPException(409, f"Ingestion job {active.id} is active; wait before changing files.")


def _existing_document(db: Session, dataset_id: str, digest: str, pending: list[Document]) -> Document | None:
    for document in pending:
        if document.sha256 == digest:
            return document
    return db.query(Document).filter(Document.dataset_id == dataset_id, Document.sha256 == digest).first()


def _upload_payload(upload: UploadFile, digest: str) -> dict:
    return {"file_name": upload.filename or "", "file_type": upload.content_type or "", "sha256": digest}


def _delete_answers_citing_document(db: Session, dataset_id: str, document_id: str) -> int:
    removed = 0
    answers = db.query(AgentAnswer).filter(AgentAnswer.dataset_id == dataset_id).all()
    for answer in answers:
        if _answer_cites_document(answer, document_id):
            db.delete(answer)
            removed += 1
    return removed


def _answer_cites_document(answer: AgentAnswer, document_id: str) -> bool:
    citations = answer.citations_json if isinstance(answer.citations_json, list) else []
    return any(isinstance(item, dict) and item.get("document_id") == document_id for item in citations)


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _remove_dir(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_file():
            _unlink(child)
    try:
        path.rmdir()
    except OSError:
        pass
