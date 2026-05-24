from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .analysis_index import analysis_index_rows
from .connection_urls import connection_url
from .db import get_db
from .load_modes import is_analysis_only
from .materialization_verify import verify_materialization
from .models import DatabaseConnection, Dataset, LoadPlan, TableCatalog
from .row_identity import stable_row_id
from .row_quarantine import quarantine_report
from .row_review import row_review_counts, row_is_loadable
from .source_integrity import source_warnings_by_row

router = APIRouter()


@router.get("/datasets/{dataset_id}/reconciliation")
def dataset_reconciliation(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found")
    plans = (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id, LoadPlan.status == "loaded")
        .order_by(LoadPlan.updated_at.desc())
        .all()
    )
    rows = [_reconcile_plan(db, plan) for plan in plans]
    return {
        "dataset_id": dataset_id,
        "status": _reconciliation_status(rows),
        "counts": {
            "loaded_plans": len(rows),
            "ready": sum(1 for row in rows if row["status"] == "ready"),
            "attention": sum(1 for row in rows if row["status"] != "ready"),
        },
        "plans": rows,
    }


@router.get("/load-plans/{plan_id}/report")
def load_plan_report(plan_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    agent = plan.agent_preparation_json or {}
    report = {
        "plan_id": plan.id,
        "dataset_id": plan.dataset_id,
        "status": plan.status,
        "destination": _destination(plan, agent),
        "preview": _preview(plan),
        "issues": plan.validation_issues or [],
        "agent": agent,
        "exports": _exports(plan),
        "live_verification": None,
    }
    if plan.status == "loaded":
        report["live_verification"] = _live_verification(db, plan, agent)
    return report


@router.get("/load-plans/{plan_id}/quarantine")
def load_plan_quarantine(plan_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    rows = plan.preview_rows or []
    report = quarantine_report(rows, source_warnings_by_row(db, plan.dataset_id, rows))
    return {
        "plan_id": plan.id,
        "dataset_id": plan.dataset_id,
        "status": plan.status,
        **report,
    }


def _destination(plan: LoadPlan, agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "connection_id": plan.connection_id or agent.get("connection_id"),
        "schema_name": plan.schema_name,
        "target_table": plan.target_table,
        "chunk_table": agent.get("chunk_table"),
        "target_mode": plan.target_mode,
    }


def _preview(plan: LoadPlan) -> dict[str, Any]:
    rows = plan.preview_rows or []
    return {
        "rows": len(rows),
        "loadable_rows": sum(1 for row in rows if row_is_loadable(row)),
        "row_review": row_review_counts(rows),
        "source_documents": sorted({str(row.get("source_document_id")) for row in rows if row.get("source_document_id")}),
    }


def _exports(plan: LoadPlan) -> dict[str, Any]:
    if plan.status != "loaded":
        return {"csv": None, "json": None}
    return {
        "csv": f"/load-plans/{plan.id}/export.csv",
        "json": f"/load-plans/{plan.id}/export.json",
    }


def _live_verification(db: Session, plan: LoadPlan, agent: dict[str, Any]) -> dict[str, Any] | None:
    chunk_table = str(agent.get("chunk_table") or "")
    if not chunk_table:
        return None
    connection = _connection(db, plan)
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    rows = analysis_index_rows(db, plan) if is_analysis_only(plan.target_mode, plan.target_table) else [row for row in plan.preview_rows or [] if row_is_loadable(row)]
    chunk_ids = [stable_row_id(row) for row in rows]
    with engine.begin() as conn:
        return verify_materialization(
            conn,
            plan.schema_name,
            plan.target_table,
            chunk_table,
            chunk_ids,
            int(agent.get("inserted_records") or 0),
            int(agent.get("inserted_chunks") or 0),
            bool(agent.get("bm25")),
            str(agent.get("embedding_status") or ""),
            target_required=plan.target_mode != "analysis_only",
        )


def _reconcile_plan(db: Session, plan: LoadPlan) -> dict[str, Any]:
    agent = plan.agent_preparation_json or {}
    try:
        verification = _live_verification(db, plan, agent)
        failures = _critical_failures(verification or {})
    except Exception as exc:
        verification = None
        failures = [f"verification_error:{str(exc)[:160]}"]
    catalog_issues = _catalog_issues(db, plan, agent)
    status = "ready" if verification and verification.get("status") == "ready" and not failures and not catalog_issues else "attention"
    return {
        "plan_id": plan.id,
        "status": status,
        "schema_name": plan.schema_name,
        "target_table": plan.target_table,
        "target_mode": plan.target_mode,
        "chunk_table": agent.get("chunk_table"),
        "critical_failures": failures,
        "catalog_issues": catalog_issues,
        "verification": verification,
    }


def _catalog_issues(db: Session, plan: LoadPlan, agent: dict[str, Any]) -> list[str]:
    row = (
        db.query(TableCatalog)
        .filter(TableCatalog.connection_id == (plan.connection_id or agent.get("connection_id")))
        .filter(TableCatalog.schema_name == plan.schema_name)
        .filter(TableCatalog.table_name == plan.target_table)
        .first()
    )
    if not row:
        return ["catalog_missing"]
    profile = row.agent_profile_json or {}
    issues = []
    if profile.get("chunk_table") != agent.get("chunk_table"):
        issues.append("catalog_chunk_table_mismatch")
    if int(profile.get("inserted_chunks") or 0) < int(agent.get("inserted_chunks") or 0):
        issues.append("catalog_inserted_chunks_stale")
    return issues


def _critical_failures(verification: dict[str, Any]) -> list[str]:
    checks = verification.get("checks") if isinstance(verification.get("checks"), list) else []
    return [str(check.get("code")) for check in checks if check.get("critical") and not check.get("ok")]


def _reconciliation_status(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "pending"
    return "ready" if all(row["status"] == "ready" for row in rows) else "needs_attention"


def _connection(db: Session, plan: LoadPlan) -> DatabaseConnection:
    connection = db.get(DatabaseConnection, plan.connection_id) if plan.connection_id else None
    connection = connection or db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()
    if not connection:
        raise HTTPException(400, "Database connection is not configured")
    return connection
