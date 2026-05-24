from typing import Any

from sqlalchemy.orm import Session

from .models import LoadPlan, LoadPlanEvent
from .parsers.common import clean_json, clean_text


def record_load_event(
    db: Session,
    plan: LoadPlan,
    action: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        LoadPlanEvent(
            load_plan_id=plan.id,
            action=clean_text(action),
            message=clean_text(message),
            payload_json=clean_json(payload or {}),
        )
    )


def load_event_payload(plan: LoadPlan, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "status": plan.status,
        "target_mode": plan.target_mode,
        "target_table": plan.target_table,
        "schema_version_id": plan.schema_version_id,
        "schema_name": plan.schema_name,
        "preview_rows": len(plan.preview_rows or []),
        "validation_issues": plan.validation_issues or [],
    }
    if extra:
        payload.update(clean_json(extra))
    return payload
