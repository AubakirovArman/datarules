from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .db import get_db
from .load_audit import load_event_payload, record_load_event
from .load_explain import attach_preview_explainability, build_agent_preparation_plan
from .load_freshness import attach_source_snapshot
from .load_preview_diff import diff_load_preview
from .load_schema_guard import schema_approval_issues, schema_identifier_issues
from .load_validation import validation_issues
from .models import DatabaseConnection, LoadPlan
from .normalization import prepare_load_preview
from .schemas import LoadPlanOut

router = APIRouter()


@router.post("/load-plans/{plan_id}/rebuild-preview", response_model=LoadPlanOut)
def rebuild_load_plan_preview(plan_id: str, db: Session = Depends(get_db)) -> LoadPlan:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    if plan.status == "loaded":
        raise HTTPException(400, "Loaded plans cannot be rebuilt; create a new load plan.")
    connection = _target_connection(db, plan.connection_id)
    rows, schema_json, issues = _fresh_preview(db, plan, connection)
    plan.schema_json = schema_json
    plan.preview_rows = rows
    plan.validation_issues = issues
    plan.agent_preparation_json = build_agent_preparation_plan(
        connection,
        plan.schema_name,
        plan.target_table,
        schema_json,
        rows,
        issues,
    )
    plan.status = "blocked" if any(issue.get("severity") == "error" for issue in issues) else "needs_confirmation"
    plan.updated_at = datetime.utcnow()
    record_load_event(db, plan, "preview_rebuilt", "Load preview rebuilt from current documents and routing.", load_event_payload(plan))
    record_audit_event(db, "load_plan.preview_rebuilt", "load_plan", plan.id, plan.dataset_id, load_event_payload(plan))
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/load-plans/{plan_id}/preview-diff")
def load_plan_preview_diff(plan_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    connection = _target_connection(db, plan.connection_id)
    fresh_rows, _, fresh_issues = _fresh_preview(db, plan, connection)
    return diff_load_preview(plan.preview_rows or [], fresh_rows, plan.validation_issues or [], fresh_issues)


def _fresh_preview(
    db: Session,
    plan: LoadPlan,
    connection: DatabaseConnection | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    rows, schema_json, extraction_issues = prepare_load_preview(
        db,
        plan.dataset_id,
        connection,
        plan.schema_name,
        plan.target_mode,
        plan.target_table,
        _schema_for_rebuild(plan),
        _document_scope(plan.schema_json),
    )
    rows = attach_preview_explainability(rows, schema_json)
    schema_json = attach_source_snapshot(db, plan.dataset_id, schema_json, rows)
    issues = _issues(db, plan, connection, rows, schema_json, extraction_issues)
    return rows, schema_json, issues


def _schema_for_rebuild(plan: LoadPlan) -> dict[str, Any]:
    schema = dict(plan.schema_json or {})
    schema.pop("source_snapshot", None)
    schema.pop("document_scope", None)
    return schema


def _document_scope(schema_json: dict[str, Any] | None) -> list[str]:
    scope = (schema_json or {}).get("document_scope")
    ids = scope.get("document_ids") if isinstance(scope, dict) else None
    return [str(item) for item in ids] if isinstance(ids, list) else []


def _issues(
    db: Session,
    plan: LoadPlan,
    connection: DatabaseConnection | None,
    rows: list[dict[str, Any]],
    schema_json: dict[str, Any],
    extraction_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return (
        extraction_issues
        + schema_identifier_issues(plan.schema_name, plan.target_table, schema_json)
        + schema_approval_issues(db, plan.dataset_id, plan.target_mode, plan.schema_version_id, schema_json)
        + validation_issues(db, plan.dataset_id, rows, connection, plan.schema_name, plan.target_mode, plan.target_table, schema_json)
    )


def _target_connection(db: Session, connection_id: str | None) -> DatabaseConnection | None:
    if connection_id:
        return db.get(DatabaseConnection, connection_id)
    return db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()
