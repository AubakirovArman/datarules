from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent
from .parsers.common import clean_json, clean_text


def record_audit_event(
    db: Session,
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    dataset_id: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: str = "system",
) -> AuditEvent:
    event = AuditEvent(
        actor=clean_text(actor)[:120],
        action=clean_text(action)[:120],
        entity_type=clean_text(entity_type)[:80],
        entity_id=clean_text(entity_id),
        dataset_id=clean_text(dataset_id) if dataset_id else None,
        payload_json=clean_json(payload or {}),
    )
    db.add(event)
    return event


def audit_event_dict(event: AuditEvent) -> dict[str, Any]:
    created_at = event.created_at
    return {
        "id": event.id,
        "actor": event.actor,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "dataset_id": event.dataset_id,
        "payload_json": event.payload_json or {},
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
    }
