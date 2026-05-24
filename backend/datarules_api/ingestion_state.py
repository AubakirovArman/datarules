from sqlalchemy.orm import Session

from .models import IngestionJob

ACTIVE_STATUSES = ("queued", "running", "cancelling")
TERMINAL_STATUSES = ("waiting_review", "completed", "failed", "cancelled")


def active_ingestion_job(db: Session, dataset_id: str) -> IngestionJob | None:
    return (
        db.query(IngestionJob)
        .filter(IngestionJob.dataset_id == dataset_id)
        .filter(IngestionJob.status.in_(ACTIVE_STATUSES))
        .order_by(IngestionJob.created_at.desc())
        .first()
    )
