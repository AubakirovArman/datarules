from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .load_audit import load_event_payload, record_load_event
from .models import LoadPlan


def invalidate_plans_for_deleted_document(
    db: Session,
    dataset_id: str,
    document_id: str,
    file_name: str,
) -> list[dict[str, Any]]:
    changed = []
    plans = db.query(LoadPlan).filter(LoadPlan.dataset_id == dataset_id).all()
    for plan in plans:
        if not _references_document(plan, document_id):
            continue
        issue = _issue(document_id, file_name)
        plan.validation_issues = _merge_issue(plan.validation_issues or [], issue)
        plan.status = "blocked"
        plan.updated_at = datetime.utcnow()
        record_load_event(db, plan, "source_deleted", issue["message"], load_event_payload(plan, issue))
        changed.append({"id": plan.id, "target_table": plan.target_table, "status": plan.status})
    return changed


def invalidate_plans_for_routing_change(
    db: Session,
    dataset_id: str,
    document_id: str,
) -> list[dict[str, Any]]:
    changed = []
    plans = (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id)
        .filter(LoadPlan.status != "loaded")
        .all()
    )
    for plan in plans:
        if not _references_document(plan, document_id):
            continue
        issue = _routing_issue(document_id)
        plan.validation_issues = _merge_issue(plan.validation_issues or [], issue)
        plan.status = "blocked"
        plan.updated_at = datetime.utcnow()
        record_load_event(db, plan, "routing_changed", issue["message"], load_event_payload(plan, issue))
        changed.append({"id": plan.id, "target_table": plan.target_table, "status": plan.status})
    return changed


def invalidate_plans_for_repaired_document(
    db: Session,
    dataset_id: str,
    document_id: str,
    file_name: str,
) -> list[dict[str, Any]]:
    changed = []
    plans = db.query(LoadPlan).filter(LoadPlan.dataset_id == dataset_id).all()
    for plan in plans:
        if not _references_document(plan, document_id):
            continue
        issue = _repair_issue(document_id, file_name)
        plan.validation_issues = _merge_issue(plan.validation_issues or [], issue)
        plan.status = "blocked"
        plan.updated_at = datetime.utcnow()
        record_load_event(db, plan, "source_repaired", issue["message"], load_event_payload(plan, issue))
        changed.append({"id": plan.id, "target_table": plan.target_table, "status": plan.status})
    return changed


def _references_document(plan: LoadPlan, document_id: str) -> bool:
    rows = plan.preview_rows if isinstance(plan.preview_rows, list) else []
    if any(isinstance(row, dict) and row.get("source_document_id") == document_id for row in rows):
        return True
    scope = (plan.schema_json or {}).get("document_scope")
    ids = scope.get("document_ids") if isinstance(scope, dict) else None
    return isinstance(ids, list) and document_id in {str(item) for item in ids}


def _issue(document_id: str, file_name: str) -> dict[str, Any]:
    return {
        "severity": "error",
        "code": "source_deleted",
        "document_id": document_id,
        "file_name": file_name,
        "message": "A source document used by this preview was deleted. Rebuild preview before loading.",
    }


def _routing_issue(document_id: str) -> dict[str, Any]:
    return {
        "severity": "error",
        "code": "routing_changed",
        "document_id": document_id,
        "message": "Document routing changed after this preview was created. Rebuild preview before loading.",
    }


def _repair_issue(document_id: str, file_name: str) -> dict[str, Any]:
    return {
        "severity": "error",
        "code": "source_repaired",
        "document_id": document_id,
        "file_name": file_name,
        "message": "A source document was re-extracted. Rebuild preview before loading.",
    }


def _merge_issue(issues: list[dict[str, Any]], issue: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        item for item in issues
        if item.get("code") != issue["code"] or item.get("document_id") != issue["document_id"]
    ]
    rows.append(issue)
    return rows
