from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .db import get_db
from .ingestion_state import TERMINAL_STATUSES
from .job_runner import submit_ingestion_job
from .models import IngestionJob, JobEvent
from .schemas import JobOut

router = APIRouter()


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> IngestionJob:
    job = db.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status in TERMINAL_STATUSES:
        return job
    job.status = "cancelling"
    job.current_stage = "cancelling"
    job.updated_at = datetime.utcnow()
    db.add(JobEvent(job_id=job.id, stage="cancelling", message="Cancellation requested.", progress_percent=job.completed_steps * 12))
    record_audit_event(
        db,
        "ingestion_job.cancel_requested",
        "ingestion_job",
        job.id,
        job.dataset_id,
        {"processed_files": job.processed_files, "total_files": job.total_files},
    )
    db.commit()
    db.refresh(job)
    submit_ingestion_job(job.id)
    return job
