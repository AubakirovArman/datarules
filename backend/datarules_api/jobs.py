from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .audit import record_audit_event
from .ai_summaries import document_ai_summary
from .config import get_settings
from .db import SessionLocal
from .extraction_runs import PARSER_VERSION, record_extraction_run, write_current_canonical
from .ingestion_state import TERMINAL_STATUSES
from .llm import GemmaClient
from .models import Document, DocumentBlock, IngestionJob, JobEvent, SchemaProposal
from .parsers import parse_document
from .parsers.common import CanonicalBlock, ParserError, clean_json, clean_text
from .routing import create_document_review
from .vision_extraction import enrich_image_pages


def run_ingestion_job(job_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if not job:
            return
        if _is_cancelling(db, job):
            _cancel_job(db, job)
            return
        if not _start_attempt(db, job):
            return
        documents = db.query(Document).filter(Document.dataset_id == job.dataset_id).all()
        job.total_files = len(documents)
        _event(db, job, "file_detection", "Starting document extraction", 5)

        snippets: list[dict[str, Any]] = []
        for index, document in enumerate(documents, start=1):
            if _is_cancelling(db, job):
                _cancel_job(db, job)
                return
            _process_document(db, document, snippets)
            if _is_cancelling(db, job):
                _cancel_job(db, job)
                return
            job.processed_files = index
            percent = 10 + int(45 * index / max(len(documents), 1))
            _event(db, job, "extraction", f"Processed {document.file_name}", percent)

        if _is_cancelling(db, job):
            _cancel_job(db, job)
            return
        _event(db, job, "schema_inference", "Preparing schema proposal", 65)
        proposal_json = GemmaClient(settings).propose_schema_sync(snippets)
        if _is_cancelling(db, job):
            _cancel_job(db, job)
            return
        proposal = SchemaProposal(dataset_id=job.dataset_id, proposal_json=proposal_json)
        db.add(proposal)
        db.flush()
        _event(db, job, "validation", "Schema proposal stored", 82, {"proposal_id": proposal.id})

        if _is_cancelling(db, job):
            _cancel_job(db, job)
            return
        _event(db, job, "indexing", "Canonical data ready for search/indexing", 95)
        job.status = "waiting_review"
        job.current_stage = "waiting_review"
        job.completed_steps = job.total_steps
        job.updated_at = datetime.utcnow()
        record_audit_event(
            db,
            "ingestion_job.finished",
            "ingestion_job",
            job.id,
            job.dataset_id,
            {"processed_files": job.processed_files, "proposal_id": proposal.id},
        )
        db.commit()
        _event(db, job, "completed", "Ingestion finished; schema awaits review", 100)
    except Exception as exc:
        db.rollback()
        job = db.get(IngestionJob, job_id)
        if job:
            job.status = "failed"
            job.current_stage = "failed"
            job.error_message = clean_text(str(exc))
            job.updated_at = datetime.utcnow()
            db.add(JobEvent(job_id=job.id, stage="failed", message=clean_text(str(exc)), progress_percent=100))
            record_audit_event(
                db,
                "ingestion_job.failed",
                "ingestion_job",
                job.id,
                job.dataset_id,
                {"error": job.error_message},
            )
            db.commit()
    finally:
        db.close()


def _process_document(db: Session, document: Document, snippets: list[dict[str, Any]], run_type: str = "ingestion") -> None:
    settings = get_settings()
    path = Path(document.storage_path)
    image_dir = settings.page_image_dir / document.id

    db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).delete()
    error_message = ""
    try:
        result = parse_document(path, document.file_type, image_dir)
        result.blocks = enrich_image_pages(result.blocks)
        document.status = "extracted"
    except ParserError as exc:
        error_message = str(exc)
        result = _error_result(str(exc))
        document.status = "needs_review"

    db_blocks: list[DocumentBlock] = []
    for block in result.blocks:
        db_block = _to_model(document.id, block)
        db.add(db_block)
        db_blocks.append(db_block)
    db.flush()
    ai_summary = document_ai_summary(db, document, db_blocks)
    create_document_review(db, document, db_blocks, ai_summary)

    canonical = _canonical_json(document, result.file_type, result.metadata, db_blocks, run_type)
    write_current_canonical(document.id, canonical)
    record_extraction_run(db, document, db_blocks, canonical, run_type, document.status, error_message)

    snippets.extend(_snippets(document, db_blocks))
    db.commit()


def _to_model(document_id: str, block: CanonicalBlock) -> DocumentBlock:
    table_json = clean_json(block.table_json)
    if block.metadata:
        table_json = {"data": table_json, "metadata": clean_json(block.metadata)}
    return DocumentBlock(
        document_id=document_id,
        page=block.page,
        sheet_name=clean_text(block.sheet_name) if block.sheet_name else None,
        slide_number=block.slide_number,
        block_type=clean_text(block.block_type),
        text=clean_text(block.text),
        table_json=table_json,
        bbox=block.bbox,
        confidence=block.confidence,
    )


def _canonical_json(
    document: Document,
    file_type: str,
    metadata: dict[str, Any],
    blocks: list[DocumentBlock],
    run_type: str,
) -> dict[str, Any]:
    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "file_type": file_type,
        "document_status": document.status,
        "parser_version": PARSER_VERSION,
        "run_type": run_type,
        "sha256": document.sha256,
        "metadata": clean_json(metadata),
        "blocks": [
            {
                "block_id": block.id,
                "type": block.block_type,
                "page": block.page,
                "sheet_name": block.sheet_name,
                "slide_number": block.slide_number,
                "text": block.text,
                "table_json": block.table_json,
                "bbox": block.bbox,
                "confidence": block.confidence,
            }
            for block in blocks
        ],
    }


def _snippets(document: Document, blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    rows = []
    for block in blocks[:30]:
        rows.append(
            {
                "file_name": document.file_name,
                "document_id": document.id,
                "block_id": block.id,
                "block_type": block.block_type,
                "page": block.page,
                "sheet_name": block.sheet_name,
                "text": block.text[:1200],
                "confidence": block.confidence,
            }
        )
    return rows


def _error_result(message: str) -> Any:
    safe_message = clean_text(message)
    block = CanonicalBlock(block_type="error", text=safe_message, confidence=0.0)
    return type("Result", (), {"file_type": "unsupported", "metadata": {"error": safe_message}, "blocks": [block]})


def _is_cancelling(db: Session, job: IngestionJob) -> bool:
    db.refresh(job)
    return job.status == "cancelling"


def _cancel_job(db: Session, job: IngestionJob) -> None:
    if job.status in TERMINAL_STATUSES:
        return
    job.status = "cancelled"
    job.current_stage = "cancelled"
    job.updated_at = datetime.utcnow()
    db.add(JobEvent(job_id=job.id, stage="cancelled", message="Ingestion cancelled by user.", progress_percent=100))
    record_audit_event(
        db,
        "ingestion_job.cancelled",
        "ingestion_job",
        job.id,
        job.dataset_id,
        {"processed_files": job.processed_files, "total_files": job.total_files},
    )
    db.commit()


def _start_attempt(db: Session, job: IngestionJob) -> bool:
    db.refresh(job)
    if int(job.attempt_count or 0) >= int(job.max_attempts or 1):
        job.status = "failed"
        job.current_stage = "failed"
        job.error_message = "Ingestion retry limit reached."
        job.updated_at = datetime.utcnow()
        db.add(JobEvent(job_id=job.id, stage="retry_limit", message=job.error_message, progress_percent=100))
        db.commit()
        return False
    job.attempt_count = int(job.attempt_count or 0) + 1
    job.heartbeat_at = datetime.utcnow()
    job.updated_at = job.heartbeat_at
    db.add(JobEvent(
        job_id=job.id,
        stage="attempt_started",
        message=f"Ingestion attempt {job.attempt_count}/{job.max_attempts}.",
        progress_percent=max(0, job.completed_steps * 12),
        payload_json={"attempt": job.attempt_count, "max_attempts": job.max_attempts},
    ))
    db.commit()
    return True


def _event(
    db: Session,
    job: IngestionJob,
    stage: str,
    message: str,
    progress: int,
    payload: Any | None = None,
) -> None:
    db.refresh(job)
    if job.status == "cancelling" or (job.status in TERMINAL_STATUSES and stage != "completed"):
        return
    job.status = "running" if stage not in {"completed", "failed"} else job.status
    job.current_stage = clean_text(stage)
    job.completed_steps = max(job.completed_steps, min(job.total_steps, progress // 12))
    job.updated_at = datetime.utcnow()
    job.heartbeat_at = job.updated_at
    db.add(
        JobEvent(
            job_id=job.id,
            stage=clean_text(stage),
            message=clean_text(message),
            progress_percent=progress,
            payload_json=clean_json(payload),
        )
    )
    db.commit()
