from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .db_identifiers import identifier_issues
from .load_audit import load_event_payload, record_load_event
from .models import LoadPlan, SchemaProposal


def schema_identifier_issues(schema_name: str, target_table: str, schema_json: dict) -> list[dict]:
    return identifier_issues(schema_name, target_table, schema_json)


def schema_approval_issues(
    db: Session,
    dataset_id: str,
    target_mode: str,
    schema_version_id: str | None,
    schema_json: dict,
) -> list[dict]:
    if _schema_is_authorized(db, dataset_id, target_mode, schema_version_id, schema_json):
        return []
    return [{
        "severity": "error",
        "code": "schema_not_approved",
        "message": "New table loads require an approved schema version or explicit user schema.",
    }]


def block_bad_plan_identifiers(db: Session, plan: LoadPlan) -> None:
    issues = schema_identifier_issues(plan.schema_name, plan.target_table, plan.schema_json or {})
    if not issues:
        return
    plan.validation_issues = _merge_schema_issues(plan.validation_issues or [], issues)
    plan.status = "blocked"
    plan.updated_at = datetime.utcnow()
    record_load_event(
        db,
        plan,
        "schema_identifier_error",
        "Schema contains unsafe database identifiers",
        load_event_payload(plan, {"issues": issues}),
    )
    db.commit()
    raise HTTPException(400, "Resolve schema identifier errors before loading")


def block_missing_schema_approval(db: Session, plan: LoadPlan) -> None:
    issues = schema_approval_issues(db, plan.dataset_id, plan.target_mode, plan.schema_version_id, plan.schema_json or {})
    if not issues:
        return
    plan.validation_issues = _merge_code_issues(plan.validation_issues or [], issues, {"schema_not_approved"})
    plan.status = "blocked"
    plan.updated_at = datetime.utcnow()
    record_load_event(db, plan, "schema_not_approved", issues[0]["message"], load_event_payload(plan, {"issues": issues}))
    db.commit()
    raise HTTPException(400, "Approve or provide a schema before loading")


def _merge_schema_issues(current: list[dict], issues: list[dict]) -> list[dict]:
    rows = [item for item in current if not str(item.get("code", "")).endswith("_identifier")]
    rows = [item for item in rows if item.get("code") not in {"duplicate_target_column", "reserved_target_column"}]
    return [*rows, *issues]


def _merge_code_issues(current: list[dict], issues: list[dict], codes: set[str]) -> list[dict]:
    return [item for item in current if item.get("code") not in codes] + issues


def _schema_is_authorized(
    db: Session,
    dataset_id: str,
    target_mode: str,
    schema_version_id: str | None,
    schema_json: dict,
) -> bool:
    if target_mode != "new":
        return True
    if not db.query(SchemaProposal.id).filter(SchemaProposal.dataset_id == dataset_id).first():
        return True
    if schema_version_id or schema_json.get("schema_version") or schema_json.get("schema_version_source"):
        return True
    return schema_json.get("schema_source") == "user_supplied_schema"
