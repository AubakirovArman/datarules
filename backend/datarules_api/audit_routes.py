from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .audit import audit_event_dict
from .db import get_db
from .models import AuditEvent

router = APIRouter()


@router.get("/audit-events")
def list_audit_events(
    dataset_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict]:
    return _events(db, dataset_id, limit)


@router.get("/datasets/{dataset_id}/audit-events")
def list_dataset_audit_events(
    dataset_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict]:
    return _events(db, dataset_id, limit)


def _events(db: Session, dataset_id: str | None, limit: int) -> list[dict]:
    query = db.query(AuditEvent)
    if dataset_id:
        query = query.filter(AuditEvent.dataset_id == dataset_id)
    rows = query.order_by(AuditEvent.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return [audit_event_dict(row) for row in rows]
