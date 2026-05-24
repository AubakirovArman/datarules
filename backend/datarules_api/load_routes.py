from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .agent_infra import materialize_load_plan
from .db import get_db
from .db_identifiers import first_identifier_error
from .field_provenance import normalize_field_sources
from .load_audit import load_event_payload, record_load_event
from .load_explain import attach_preview_explainability, build_agent_preparation_plan
from .load_freshness import attach_source_snapshot, merge_stale_issue, stale_preview_issue
from .load_plan_backfill import ensure_field_sources
from .load_plan_request import LoadPlanCreate, schema_for_load_plan
from .load_schema_guard import block_bad_plan_identifiers, block_missing_schema_approval, schema_approval_issues, schema_identifier_issues
from .load_validation import validation_issues
from .models import DatabaseConnection, Dataset, LoadPlan
from .normalization import prepare_load_preview
from .parsers.common import clean_json, clean_text
from .row_review import normalize_row_status
from .schemas import LoadPlanOut, LoadPlanPreviewUpdate
from .write_policy import connection_can_write, write_denial

router = APIRouter()


@router.get("/datasets/{dataset_id}/load-plans", response_model=list[LoadPlanOut])
def list_load_plans(dataset_id: str, db: Session = Depends(get_db)) -> list[LoadPlan]:
    _require_dataset(db, dataset_id)
    plans = db.query(LoadPlan).filter(LoadPlan.dataset_id == dataset_id).order_by(LoadPlan.created_at.desc()).all()
    if any([ensure_field_sources(plan) for plan in plans]):
        db.commit()
    return plans


@router.post("/datasets/{dataset_id}/load-plans", response_model=LoadPlanOut)
def create_load_plan(dataset_id: str, payload: LoadPlanCreate, db: Session = Depends(get_db)) -> LoadPlan:
    _require_dataset(db, dataset_id)
    plan_schema = schema_for_load_plan(db, dataset_id, payload)
    if error := first_identifier_error(payload.schema_name, payload.target_table.strip(), plan_schema):
        raise HTTPException(400, error)
    connection = _target_connection(db, payload.connection_id)
    preview_rows, schema_json, extraction_issues = prepare_load_preview(
        db,
        dataset_id,
        connection,
        payload.schema_name,
        payload.target_mode,
        payload.target_table.strip(),
        plan_schema,
        payload.document_ids,
    )
    preview_rows = attach_preview_explainability(preview_rows, schema_json)
    schema_json = attach_source_snapshot(db, dataset_id, schema_json, preview_rows)
    schema_issues = schema_identifier_issues(payload.schema_name, payload.target_table.strip(), schema_json)
    approval_issues = schema_approval_issues(db, dataset_id, payload.target_mode, payload.schema_version_id, schema_json)
    issues = validation_issues(db, dataset_id, preview_rows, connection, payload.schema_name, payload.target_mode, payload.target_table, schema_json)
    issues = extraction_issues + schema_issues + approval_issues + issues
    plan = LoadPlan(
        dataset_id=dataset_id,
        connection_id=connection.id if connection else None,
        schema_version_id=payload.schema_version_id,
        schema_name=payload.schema_name,
        target_mode=payload.target_mode,
        target_table=payload.target_table.strip(),
        schema_json=schema_json,
        preview_rows=preview_rows,
        validation_issues=issues,
        agent_preparation_json=build_agent_preparation_plan(
            connection,
            payload.schema_name,
            payload.target_table.strip(),
            schema_json,
            preview_rows,
            issues,
        ),
        status="blocked" if any(issue["severity"] == "error" for issue in issues) else "needs_confirmation",
    )
    db.add(plan)
    db.flush()
    record_load_event(
        db,
        plan,
        "created",
        "Load preview created",
        load_event_payload(plan, {"extraction_issues": extraction_issues}),
    )
    record_audit_event(
        db,
        "load_plan.created",
        "load_plan",
        plan.id,
        dataset_id,
        load_event_payload(plan, {"document_ids": payload.document_ids, "schema_version_id": payload.schema_version_id, "extraction_issues": extraction_issues}),
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/load-plans/{plan_id}/confirm", response_model=LoadPlanOut)
def confirm_load_plan(plan_id: str, db: Session = Depends(get_db)) -> LoadPlan:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    if ensure_field_sources(plan):
        db.commit()
        db.refresh(plan)
    if plan.status == "loaded":
        return plan
    connection = _target_connection(db, plan.connection_id)
    block_bad_plan_identifiers(db, plan)
    stale_issue = stale_preview_issue(db, plan)
    if stale_issue:
        plan.validation_issues = merge_stale_issue(plan.validation_issues or [], stale_issue)
        plan.status = "blocked"
        plan.updated_at = datetime.utcnow()
        record_load_event(db, plan, "stale_preview", stale_issue["message"], load_event_payload(plan, stale_issue))
        record_audit_event(
            db,
            "load_plan.stale_preview",
            "load_plan",
            plan.id,
            plan.dataset_id,
            load_event_payload(plan, stale_issue),
        )
        db.commit()
        raise HTTPException(400, stale_issue["message"])
    block_missing_schema_approval(db, plan)
    if not connection_can_write(connection, plan.schema_name):
        raise HTTPException(400, write_denial(connection, plan.schema_name)["message"])
    _block_current_validation_errors(db, plan, connection)
    try:
        plan.agent_preparation_json = materialize_load_plan(db, plan)
    except Exception as exc:
        db.rollback()
        plan = _block_materialization_failure(db, plan_id, exc)
        raise HTTPException(400, "Materialization failed; check load plan events.") from exc
    plan.status = "loaded"
    plan.updated_at = datetime.utcnow()
    record_load_event(
        db,
        plan,
        "loaded",
        "Load plan confirmed and materialized",
        load_event_payload(plan, {"agent_preparation": plan.agent_preparation_json}),
    )
    record_audit_event(
        db,
        "load_plan.loaded",
        "load_plan",
        plan.id,
        plan.dataset_id,
        load_event_payload(plan, {"agent_preparation": plan.agent_preparation_json}),
    )
    db.commit()
    db.refresh(plan)
    return plan


def _block_materialization_failure(db: Session, plan_id: str, exc: Exception) -> LoadPlan:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    issue = {"severity": "error", "code": "materialization_failed", "message": clean_text(str(exc))[:700]}
    plan.validation_issues = [item for item in plan.validation_issues or [] if item.get("code") != issue["code"]]
    plan.validation_issues.append(issue)
    plan.status = "blocked"
    plan.updated_at = datetime.utcnow()
    record_load_event(db, plan, "materialization_failed", issue["message"], load_event_payload(plan, issue))
    record_audit_event(db, "load_plan.materialization_failed", "load_plan", plan.id, plan.dataset_id, load_event_payload(plan, issue))
    db.commit()
    db.refresh(plan)
    return plan


def _block_current_validation_errors(db: Session, plan: LoadPlan, connection: DatabaseConnection | None) -> None:
    issues = validation_issues(db, plan.dataset_id, plan.preview_rows or [], connection, plan.schema_name, plan.target_mode, plan.target_table, plan.schema_json or {})
    plan.validation_issues = issues
    if not any(issue.get("severity") == "error" for issue in issues):
        return
    plan.status = "blocked"
    plan.updated_at = datetime.utcnow()
    record_load_event(db, plan, "preflight_failed", "Live validation failed before materialization.", load_event_payload(plan, {"issues": issues}))
    record_audit_event(db, "load_plan.preflight_failed", "load_plan", plan.id, plan.dataset_id, load_event_payload(plan, {"issues": issues}))
    db.commit()
    raise HTTPException(400, "Resolve validation errors before loading")


@router.patch("/load-plans/{plan_id}/preview-rows", response_model=LoadPlanOut)
def update_preview_rows(
    plan_id: str,
    payload: LoadPlanPreviewUpdate,
    db: Session = Depends(get_db),
) -> LoadPlan:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    if plan.status == "loaded":
        raise HTTPException(400, "Loaded plans cannot be edited")
    rows = attach_preview_explainability(_clean_preview_rows(payload.preview_rows), plan.schema_json)
    plan.preview_rows = rows
    schema_issues = schema_identifier_issues(plan.schema_name, plan.target_table, plan.schema_json or {})
    connection = _target_connection(db, plan.connection_id)
    plan.validation_issues = schema_issues + validation_issues(db, plan.dataset_id, rows, connection, plan.schema_name, plan.target_mode, plan.target_table, plan.schema_json)
    plan.agent_preparation_json = build_agent_preparation_plan(
        connection,
        plan.schema_name,
        plan.target_table,
        plan.schema_json,
        rows,
        plan.validation_issues,
    )
    plan.status = "blocked" if any(issue["severity"] == "error" for issue in plan.validation_issues) else "needs_confirmation"
    plan.updated_at = datetime.utcnow()
    record_load_event(
        db,
        plan,
        "preview_edited",
        "Preview rows edited by user",
        load_event_payload(plan, {"edited_rows": len(rows)}),
    )
    record_audit_event(
        db,
        "load_plan.preview_edited",
        "load_plan",
        plan.id,
        plan.dataset_id,
        load_event_payload(plan, {"edited_rows": len(rows)}),
    )
    db.commit()
    db.refresh(plan)
    return plan


def _clean_preview_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_clean_preview_row(row, index) for index, row in enumerate(rows[:100], start=1)]


def _clean_preview_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    field_values = row.get("field_values") if isinstance(row.get("field_values"), dict) else {}
    content = clean_text(str(row.get("content") or row.get("field_text") or _content_from_fields(field_values)))
    source_document_id = clean_text(str(row.get("source_document_id") or ""))
    source_block_id = clean_text(str(row.get("source_block_id") or ""))
    errors = []
    if not source_document_id:
        errors.append("missing_source_document_id")
    if not source_block_id:
        errors.append("missing_source_block_id")
    if not field_values or not any(value not in (None, "") for value in field_values.values()):
        errors.append("empty_field_values")
    validation_errors = sorted(set(errors + [str(item) for item in row.get("validation_errors", []) if item]))
    return {
        **clean_json(row),
        "row_id": clean_text(str(row.get("row_id") or f"manual:{index}")),
        "source_document_id": source_document_id,
        "source_block_id": source_block_id,
        "source_file": clean_text(str(row.get("source_file") or "")),
        "page": row.get("page"),
        "sheet": row.get("sheet"),
        "content": content,
        "field_text": content[:800],
        "field_values": clean_json(field_values),
        "field_sources": normalize_field_sources(row, field_values),
        "row_status": normalize_row_status({**row, "validation_errors": validation_errors}),
        "confidence": _confidence(row.get("confidence")),
        "validation_errors": validation_errors,
        "edited_by_user": True,
    }


def _content_from_fields(fields: dict[str, Any]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in fields.items() if value not in (None, ""))


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.7


def _target_connection(db: Session, connection_id: str | None) -> DatabaseConnection | None:
    if connection_id:
        return db.get(DatabaseConnection, connection_id)
    return db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()


def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset
