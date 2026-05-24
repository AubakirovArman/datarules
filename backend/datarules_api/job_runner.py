from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock

from sqlalchemy.orm import Session

from .db import SessionLocal
from .ingestion_state import ACTIVE_STATUSES
from .jobs import run_ingestion_job
from .models import IngestionJob, JobEvent
from .parsers.common import clean_text

_executor: ThreadPoolExecutor | None = None
_lock = Lock()
_submitted: set[str] = set()


def submit_ingestion_job(job_id: str) -> None:
    with _lock:
        if job_id in _submitted:
            return
        _submitted.add(job_id)
    _executor_instance().submit(_run_once, job_id)


def recover_incomplete_jobs() -> int:
    with SessionLocal() as db:
        jobs = (
            db.query(IngestionJob)
            .filter(IngestionJob.status.in_(ACTIVE_STATUSES))
            .order_by(IngestionJob.created_at)
            .all()
        )
        for job in jobs:
            if _attempts_exhausted(job):
                _mark_exhausted(db, job, "Job retry limit was reached during startup recovery.")
                continue
            db.add(JobEvent(
                job_id=job.id,
                stage="recovered",
                message="Job recovered after API startup.",
                progress_percent=max(0, job.completed_steps * 12),
                payload_json={"attempt": job.attempt_count, "max_attempts": job.max_attempts},
            ))
            if job.status != "cancelling":
                job.status = "queued"
            job.current_stage = "recovered"
            job.updated_at = datetime.utcnow()
        db.commit()
        job_ids = [job.id for job in jobs if job.status in ACTIVE_STATUSES]
    for job_id in job_ids:
        submit_ingestion_job(job_id)
    return len(job_ids)


def shutdown_job_runner() -> None:
    global _executor
    with _lock:
        executor = _executor
        _executor = None
        _submitted.clear()
    if executor:
        executor.shutdown(wait=False, cancel_futures=False)


def _executor_instance() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="datarules-ingest")
        return _executor


def _run_once(job_id: str) -> None:
    try:
        run_ingestion_job(job_id)
    except Exception as exc:
        _record_runner_failure(job_id, exc)
    finally:
        with _lock:
            _submitted.discard(job_id)
    if _schedule_retry(job_id):
        submit_ingestion_job(job_id)


def _record_runner_failure(job_id: str, exc: Exception) -> None:
    with SessionLocal() as db:
        job = db.get(IngestionJob, job_id)
        if not job:
            return
        message = clean_text(str(exc))
        job.status = "failed"
        job.current_stage = "failed"
        job.error_message = message
        db.add(JobEvent(job_id=job.id, stage="failed", message=message, progress_percent=100))
        db.commit()


def _schedule_retry(job_id: str) -> bool:
    with SessionLocal() as db:
        job = db.get(IngestionJob, job_id)
        if not job or job.status != "failed" or _attempts_exhausted(job):
            return False
        last_error = job.error_message or ""
        job.status = "queued"
        job.current_stage = "retry_scheduled"
        job.error_message = None
        job.updated_at = datetime.utcnow()
        db.add(JobEvent(
            job_id=job.id,
            stage="retry_scheduled",
            message=f"Retry scheduled after failure: {last_error[:300]}",
            progress_percent=max(0, job.completed_steps * 12),
            payload_json={"attempt": job.attempt_count, "max_attempts": job.max_attempts},
        ))
        db.commit()
        return True


def _attempts_exhausted(job: IngestionJob) -> bool:
    return int(job.attempt_count or 0) >= int(job.max_attempts or 1)


def _mark_exhausted(db: Session, job: IngestionJob, message: str) -> None:
    job.status = "failed"
    job.current_stage = "failed"
    job.error_message = message
    job.updated_at = datetime.utcnow()
    db.add(JobEvent(job_id=job.id, stage="retry_limit", message=message, progress_percent=100))
