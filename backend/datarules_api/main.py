import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .audit_routes import router as audit_router
from .config import get_settings
from .ask_routes import router as ask_router
from .db import SessionLocal, get_db, init_db
from .db_catalog import router as db_catalog_router
from .dataset_report import router as dataset_report_router
from .diagnostics import router as diagnostics_router
from .extraction_run_routes import router as extraction_run_router
from .file_routes import router as file_router
from .document_quality_routes import router as document_quality_router
from .document_repair_routes import router as document_repair_router
from .ingestion_state import active_ingestion_job
from .interactive import router as interactive_router
from .job_routes import router as job_router
from .job_runner import recover_incomplete_jobs, shutdown_job_runner, submit_ingestion_job
from .load_export import router as load_export_router
from .load_plan_invalidation import invalidate_plans_for_routing_change
from .load_report import router as load_report_router
from .load_rebuild import router as load_rebuild_router
from .load_reindex import router as load_reindex_router
from .load_routes import router as load_router
from .load_rows import router as load_rows_router
from .models import Dataset, Document, DocumentReview, IngestionJob, JobEvent, SchemaProposal
from .query_guide import router as query_guide_router
from .quality_scorecard import router as quality_scorecard_router
from .readiness import router as readiness_router
from .review_routes import router as review_router
from .routing import refresh_document_reviews
from .schema_versions import approve_schema_version, router as schema_versions_router
from .search_routes import router as search_router
from .sql_query import router as sql_query_router
from .schemas import (
    DatasetCreate,
    DatasetOut,
    DocumentReviewDecision,
    DocumentReviewOut,
    EventOut,
    JobOut,
    SchemaProposalOut,
)
from .secret_store import secret_key_status

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    recover_incomplete_jobs()
    try:
        yield
    finally:
        shutdown_job_runner()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(file_router)
app.include_router(document_quality_router)
app.include_router(document_repair_router)
app.include_router(extraction_run_router)
app.include_router(job_router)
app.include_router(interactive_router)
app.include_router(load_router)
app.include_router(load_export_router)
app.include_router(load_report_router)
app.include_router(load_rebuild_router)
app.include_router(load_reindex_router)
app.include_router(load_rows_router)
app.include_router(db_catalog_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(audit_router)
app.include_router(readiness_router)
app.include_router(diagnostics_router)
app.include_router(review_router)
app.include_router(dataset_report_router)
app.include_router(quality_scorecard_router)
app.include_router(schema_versions_router)
app.include_router(query_guide_router)
app.include_router(sql_query_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "gemma_model_id": settings.gemma_model_id,
        "gemma_base_url": settings.gemma_base_url,
        "gemma_gpu_id": settings.gemma_gpu_id,
        "live_gemma_enabled": settings.enable_gemma_calls,
        "embedding_model_id": settings.embedding_model_id,
        "embedding_base_url": settings.embedding_base_url,
        "live_embeddings_enabled": settings.enable_embedding_calls,
        "secret_storage": secret_key_status(),
    }


@app.post("/datasets", response_model=DatasetOut)
def create_dataset(payload: DatasetCreate, db: Annotated[Session, Depends(get_db)]) -> Dataset:
    dataset = Dataset(name=payload.name, description=payload.description)
    db.add(dataset)
    db.flush()
    record_audit_event(db, "dataset.created", "dataset", dataset.id, dataset.id, {"name": dataset.name})
    db.commit()
    db.refresh(dataset)
    return dataset


@app.get("/datasets", response_model=list[DatasetOut])
def list_datasets(db: Annotated[Session, Depends(get_db)]) -> list[Dataset]:
    return db.query(Dataset).order_by(Dataset.created_at.desc()).all()


@app.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, db: Annotated[Session, Depends(get_db)]) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


@app.post("/datasets/{dataset_id}/ingestion-jobs", response_model=JobOut)
def start_job(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> IngestionJob:
    _require_dataset(db, dataset_id)
    total = db.query(func.count(Document.id)).filter(Document.dataset_id == dataset_id).scalar() or 0
    if total == 0:
        raise HTTPException(400, "Upload at least one file before starting ingestion")
    active = active_ingestion_job(db, dataset_id)
    if active:
        submit_ingestion_job(active.id)
        return active

    job = IngestionJob(dataset_id=dataset_id, total_files=total, max_attempts=settings.ingestion_max_attempts)
    db.add(job)
    db.flush()
    db.add(JobEvent(job_id=job.id, stage="queued", message="Job queued", progress_percent=0))
    record_audit_event(db, "ingestion_job.started", "ingestion_job", job.id, dataset_id, {"total_files": total})
    db.commit()
    db.refresh(job)
    submit_ingestion_job(job.id)
    return job


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Annotated[Session, Depends(get_db)]) -> IngestionJob:
    job = db.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/jobs/{job_id}/events", response_model=list[EventOut])
def get_events(job_id: str, db: Annotated[Session, Depends(get_db)]) -> list[JobEvent]:
    return db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.created_at).all()


@app.get("/jobs/{job_id}/events/stream")
async def stream_events(job_id: str) -> StreamingResponse:
    async def event_source():
        last_count = -1
        while True:
            with SessionLocal() as db:
                job = db.get(IngestionJob, job_id)
                events = db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.created_at).all()
                if len(events) != last_count:
                    payload = [_event_payload(event) for event in events]
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    last_count = len(events)
                if job and job.status in {"waiting_review", "completed", "failed", "cancelled"}:
                    break
            await asyncio.sleep(1)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/datasets/{dataset_id}/schema-proposals", response_model=list[SchemaProposalOut])
def list_schema_proposals(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[SchemaProposal]:
    _require_dataset(db, dataset_id)
    return db.query(SchemaProposal).filter(SchemaProposal.dataset_id == dataset_id).all()


@app.get("/datasets/{dataset_id}/document-reviews", response_model=list[DocumentReviewOut])
def list_document_reviews(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentReviewOut]:
    _require_dataset(db, dataset_id)
    refresh_document_reviews(db, dataset_id)
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


@app.post("/document-reviews/{review_id}/decision", response_model=DocumentReviewOut)
def decide_document_review(
    review_id: str,
    payload: DocumentReviewDecision,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentReviewOut:
    review = db.get(DocumentReview, review_id)
    if not review:
        raise HTTPException(404, "Document review not found")
    review.selected_doc_type = payload.selected_doc_type
    review.selected_table = payload.selected_table
    review.notes = payload.notes
    review.status = "confirmed"
    review.updated_at = datetime.utcnow()
    invalidated = invalidate_plans_for_routing_change(db, review.dataset_id, review.document_id)
    record_audit_event(
        db,
        "document_review.confirmed",
        "document_review",
        review.id,
        review.dataset_id,
        {
            "document_id": review.document_id,
            "selected_doc_type": review.selected_doc_type,
            "selected_table": review.selected_table,
            "notes": review.notes,
            "invalidated_load_plans": invalidated,
        },
    )
    db.commit()
    db.refresh(review)
    document = db.get(Document, review.document_id)
    return DocumentReviewOut.model_validate(review).model_copy(
        update={"file_name": document.file_name if document else None}
    )


@app.post("/schema-proposals/{proposal_id}/approve", response_model=SchemaProposalOut)
def approve_schema(proposal_id: str, db: Annotated[Session, Depends(get_db)]) -> SchemaProposal:
    proposal = db.get(SchemaProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "Schema proposal not found")
    proposal.status = "approved"
    version = approve_schema_version(db, proposal)
    record_audit_event(
        db,
        "schema_proposal.approved",
        "schema_proposal",
        proposal.id,
        proposal.dataset_id,
        {"tables": len((proposal.proposal_json or {}).get("tables", [])), "schema_version_id": version.id},
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


def _event_payload(event: JobEvent) -> dict:
    return {
        "id": event.id,
        "stage": event.stage,
        "message": event.message,
        "progress_percent": event.progress_percent,
        "payload_json": event.payload_json,
        "created_at": event.created_at.isoformat() if isinstance(event.created_at, datetime) else None,
    }
