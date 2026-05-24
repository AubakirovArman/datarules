from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import get_db
from .models import Dataset, Document, DocumentAiSummary, DocumentBlock, DocumentReview, LoadPlan, SchemaProposal

router = APIRouter()


@router.get("/datasets/{dataset_id}/readiness")
def dataset_readiness(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found")
    documents = db.query(Document).filter(Document.dataset_id == dataset_id).all()
    doc_ids = [document.id for document in documents]
    counts = _counts(db, dataset_id, doc_ids, documents)
    plans = (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id)
        .order_by(LoadPlan.updated_at.desc(), LoadPlan.created_at.desc())
        .all()
    )
    stages = _stages(documents, counts, plans)
    return {
        "dataset_id": dataset_id,
        "status": _overall_status(stages),
        "score": _score(stages),
        "counts": counts,
        "stages": stages,
        "agent": _agent_state(plans),
        "next_actions": _next_actions(stages),
        "action_plan": _action_plan(stages, plans),
    }


def _counts(db: Session, dataset_id: str, doc_ids: list[str], documents: list[Document]) -> dict[str, Any]:
    reviews = db.query(DocumentReview).filter(DocumentReview.dataset_id == dataset_id).all()
    proposals = db.query(SchemaProposal).filter(SchemaProposal.dataset_id == dataset_id).all()
    block_count = _count_for_docs(db, DocumentBlock.document_id, doc_ids)
    summary_count = _count_for_docs(db, DocumentAiSummary.document_id, doc_ids)
    return {
        "documents": len(documents),
        "documents_extracted": sum(1 for document in documents if document.status == "extracted"),
        "documents_needing_review": sum(1 for document in documents if document.status == "needs_review"),
        "blocks": block_count,
        "ai_summaries": summary_count,
        "reviews": len(reviews),
        "reviews_confirmed": sum(1 for review in reviews if review.status == "confirmed"),
        "schema_proposals": len(proposals),
        "schema_approved": sum(1 for proposal in proposals if proposal.status == "approved"),
    }


def _count_for_docs(db: Session, column: Any, doc_ids: list[str]) -> int:
    if not doc_ids:
        return 0
    return int(db.query(func.count()).filter(column.in_(doc_ids)).scalar() or 0)


def _stages(documents: list[Document], counts: dict[str, Any], plans: list[LoadPlan]) -> list[dict[str, Any]]:
    latest = plans[0] if plans else None
    return [
        _stage("upload", "ready" if documents else "pending", count=counts["documents"]),
        _extraction_stage(documents, counts),
        _summary_stage(counts),
        _routing_stage(counts),
        _schema_stage(counts),
        _preview_stage(latest),
        _materialization_stage(plans),
        _retrieval_stage(plans),
    ]


def _extraction_stage(documents: list[Document], counts: dict[str, Any]) -> dict[str, Any]:
    if not documents:
        return _stage("extraction", "pending")
    if counts["documents_needing_review"]:
        return _stage("extraction", "attention", count=counts["documents_needing_review"])
    if counts["documents_extracted"] == counts["documents"] and counts["blocks"]:
        return _stage("extraction", "ready", count=counts["blocks"])
    return _stage("extraction", "pending")


def _summary_stage(counts: dict[str, Any]) -> dict[str, Any]:
    if not counts["documents"]:
        return _stage("summary", "pending")
    if counts["ai_summaries"] >= counts["documents"]:
        return _stage("summary", "ready", count=counts["ai_summaries"])
    return _stage("summary", "attention", count=counts["ai_summaries"], total=counts["documents"])


def _routing_stage(counts: dict[str, Any]) -> dict[str, Any]:
    if not counts["reviews"]:
        return _stage("routing", "pending")
    if counts["reviews_confirmed"] == counts["reviews"]:
        return _stage("routing", "ready", count=counts["reviews_confirmed"])
    return _stage("routing", "attention", count=counts["reviews_confirmed"], total=counts["reviews"])


def _schema_stage(counts: dict[str, Any]) -> dict[str, Any]:
    if counts["schema_approved"]:
        return _stage("schema", "ready", count=counts["schema_approved"])
    if counts["schema_proposals"]:
        return _stage("schema", "attention", count=counts["schema_proposals"])
    return _stage("schema", "pending")


def _preview_stage(plan: LoadPlan | None) -> dict[str, Any]:
    if not plan:
        return _stage("preview", "pending")
    rows = len(plan.preview_rows or [])
    if plan.status == "blocked":
        return _stage("preview", "blocked", count=rows)
    return _stage("preview", "ready" if rows else "attention", count=rows)


def _materialization_stage(plans: list[LoadPlan]) -> dict[str, Any]:
    loaded = [plan for plan in plans if plan.status == "loaded"]
    if loaded:
        total = sum(int((plan.agent_preparation_json or {}).get("inserted_records") or 0) for plan in loaded)
        return _stage("materialization", "ready", count=total)
    if any(_has_issue(plan, "materialization_failed") for plan in plans):
        return _stage("materialization", "blocked")
    return _stage("materialization", "pending")


def _retrieval_stage(plans: list[LoadPlan]) -> dict[str, Any]:
    tables = _agent_tables(plans)
    ready = [table for table in tables if table["ready_for_agent"]]
    if ready:
        return _stage("retrieval", "ready", count=len(ready))
    if tables:
        return _stage("retrieval", "attention", count=len(tables))
    return _stage("retrieval", "pending")


def _stage(key: str, status: str, **metrics: int) -> dict[str, Any]:
    return {"key": key, "status": status, **metrics}


def _agent_state(plans: list[LoadPlan]) -> dict[str, Any]:
    tables = _agent_tables(plans)
    return {
        "ready": any(table["ready_for_agent"] for table in tables),
        "tables": tables,
        "loaded_plans": sum(1 for plan in plans if plan.status == "loaded"),
    }


def _agent_tables(plans: list[LoadPlan]) -> list[dict[str, Any]]:
    rows = []
    for plan in plans:
        value = plan.agent_preparation_json or {}
        if plan.status != "loaded" and value.get("stage") != "materialized":
            continue
        verification = value.get("verification") if isinstance(value.get("verification"), dict) else {}
        indexes = verification.get("indexes") if isinstance(verification.get("indexes"), dict) else {}
        ready = bool(value.get("ready_for_agent") or indexes.get("full_text") or value.get("keyword_search"))
        rows.append({
            "plan_id": plan.id,
            "schema_name": plan.schema_name,
            "target_table": plan.target_table,
            "chunk_table": value.get("chunk_table"),
            "inserted_records": value.get("inserted_records", 0),
            "inserted_chunks": value.get("inserted_chunks", 0),
            "embedding_status": value.get("embedding_status"),
            "semantic_search": bool(value.get("semantic_search")),
            "bm25": bool(value.get("bm25")),
            "keyword_search": bool(value.get("keyword_search") or indexes.get("full_text")),
            "ready_for_agent": ready,
        })
    return rows


def _has_issue(plan: LoadPlan, code: str) -> bool:
    return any(issue.get("code") == code for issue in plan.validation_issues or [])


def _overall_status(stages: list[dict[str, str]]) -> str:
    if any(stage["status"] == "blocked" for stage in stages):
        return "blocked"
    if stages[-1]["status"] == "ready":
        return "ready_for_agent"
    if any(stage["status"] == "attention" for stage in stages):
        return "needs_attention"
    return "in_progress"


def _score(stages: list[dict[str, str]]) -> int:
    weights = {"ready": 1.0, "attention": 0.55, "pending": 0.0, "blocked": 0.15}
    return round(sum(weights.get(stage["status"], 0) for stage in stages) / len(stages) * 100)


def _next_actions(stages: list[dict[str, str]]) -> list[str]:
    actions = []
    for stage in stages:
        if stage["status"] != "ready":
            actions.append(f"readiness_next_{stage['key']}")
        if len(actions) == 3:
            break
    return actions


def _action_plan(stages: list[dict[str, str]], plans: list[LoadPlan]) -> list[dict[str, Any]]:
    latest = plans[0] if plans else None
    rows = []
    for stage in stages:
        if stage["status"] == "ready":
            continue
        rows.append(_action_for_stage(stage, latest))
        if len(rows) == 4:
            break
    if not rows:
        rows.append(_action("ready_for_agent", "ready", "search", "decisionOpenSearch", "decisionReady", "decisionOpenSearch"))
    return rows


def _action_for_stage(stage: dict[str, Any], plan: LoadPlan | None) -> dict[str, Any]:
    key = stage["key"]
    if key == "upload":
        return _action("upload_documents", "blocker", "upload", "actionUpload", "actionUploadDetail", "actionButtonUpload")
    if key == "extraction":
        return _action("run_extraction", "blocker", "analyze", "actionAnalyze", "actionAnalyzeDetail", "actionButtonAnalyze")
    if key == "summary":
        return _action("wait_for_summary", "warning", "summary", "actionAnalyzing", "actionAnalyzingDetail", "actionButtonAnalyzing")
    if key == "routing":
        return _action("confirm_routing", "blocker", "destination", "decisionAcceptRoutes", "decisionRouteBlocked", "actionButtonReview")
    if key == "schema":
        return _action("approve_schema", "blocker", "destination", "decisionApproveSchema", "decisionSchemaBlocked", "actionButtonSchema")
    if key == "preview":
        code = _primary_issue(plan)
        detail = code if code else "decisionLoadBlocked"
        return _action("fix_preview", "blocker", "load", "actionLoad", detail, "actionButtonLoad", plan)
    if key == "materialization":
        return _action("confirm_load", "blocker", "load", "actionLoad", "decisionLoadBlocked", "actionButtonLoad", plan)
    return _action("verify_retrieval", "warning", "search", "actionIndex", "actionIndexDetail", "actionButtonIndex", plan)


def _action(
    code: str,
    severity: str,
    step: str,
    title_key: str,
    detail_key: str,
    cta_key: str,
    plan: LoadPlan | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "step": step,
        "title_key": title_key,
        "detail_key": detail_key,
        "cta_key": cta_key,
        "load_plan_id": plan.id if plan else None,
    }


def _primary_issue(plan: LoadPlan | None) -> str | None:
    if not plan:
        return None
    issues = [issue for issue in plan.validation_issues or [] if issue.get("severity") == "error"]
    return str(issues[0].get("code")) if issues else None
