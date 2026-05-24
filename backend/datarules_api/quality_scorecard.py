from statistics import mean
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .document_quality import build_quality_profile
from .golden_gate import dataset_golden_gate
from .models import Dataset, Document, DocumentAiSummary, DocumentBlock, DocumentReview, GoldenCheck, LoadPlan, SchemaProposal
from .row_review import row_is_loadable, row_review_counts
from .source_integrity import source_reference_issues

router = APIRouter()


@router.get("/datasets/{dataset_id}/quality-scorecard")
def dataset_quality_scorecard(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found")
    documents = db.query(Document).filter(Document.dataset_id == dataset_id).all()
    doc_ids = [document.id for document in documents]
    blocks = _blocks_by_doc(db, doc_ids)
    summaries = _summaries_by_doc(db, doc_ids)
    reviews = db.query(DocumentReview).filter(DocumentReview.dataset_id == dataset_id).all()
    proposals = db.query(SchemaProposal).filter(SchemaProposal.dataset_id == dataset_id).all()
    plans = (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id)
        .order_by(LoadPlan.updated_at.desc(), LoadPlan.created_at.desc())
        .all()
    )
    golden = db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).order_by(GoldenCheck.created_at).all()
    checks = [
        _extraction_check(documents, blocks),
        _summary_check(documents, summaries),
        _routing_check(reviews),
        _schema_check(proposals),
        _preview_check(plans),
        _source_check(db, dataset_id, plans),
        _load_check(plans),
        _retrieval_check(plans),
        _golden_check(db, dataset_id, golden, plans),
    ]
    return {
        "dataset_id": dataset_id,
        "status": _overall_status(checks),
        "score": _overall_score(checks),
        "checks": checks,
        "blockers": _blockers(checks),
        "next_actions": _next_actions(checks),
    }


def _blocks_by_doc(db: Session, doc_ids: list[str]) -> dict[str, list[DocumentBlock]]:
    grouped = {document_id: [] for document_id in doc_ids}
    if not doc_ids:
        return grouped
    rows = db.query(DocumentBlock).filter(DocumentBlock.document_id.in_(doc_ids)).all()
    for row in rows:
        grouped.setdefault(row.document_id, []).append(row)
    return grouped


def _summaries_by_doc(db: Session, doc_ids: list[str]) -> dict[str, DocumentAiSummary]:
    if not doc_ids:
        return {}
    rows = db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id.in_(doc_ids)).all()
    return {row.document_id: row for row in rows}


def _extraction_check(documents: list[Document], blocks: dict[str, list[DocumentBlock]]) -> dict[str, Any]:
    if not documents:
        return _check("extraction", "pending", 0, "No documents uploaded yet.", {"documents": 0})
    profiles = [build_quality_profile(blocks.get(document.id, [])) for document in documents]
    score = round(mean(int(profile["extraction_score"]) for profile in profiles))
    weak = [document.id for document, profile in zip(documents, profiles) if profile["status"] != "ready"]
    status = "ready" if not weak and score >= 75 else "attention"
    return _check(status=status, key="extraction", score=score, detail=f"{len(blocks)} document(s) extracted.", metrics={
        "documents": len(documents),
        "blocks": sum(len(items) for items in blocks.values()),
        "weak_documents": len(weak),
    }, blockers=weak[:8])


def _summary_check(documents: list[Document], summaries: dict[str, DocumentAiSummary]) -> dict[str, Any]:
    total = len(documents)
    ready = len(summaries)
    if not total:
        return _check("gemma_summary", "pending", 0, "No documents for summary.", {"documents": 0})
    status = "ready" if ready >= total else "attention"
    return _check("gemma_summary", status, round(ready / total * 100), f"{ready}/{total} summaries ready.", {
        "documents": total,
        "summaries": ready,
    })


def _routing_check(reviews: list[DocumentReview]) -> dict[str, Any]:
    if not reviews:
        return _check("routing", "pending", 0, "No routing decisions yet.", {"reviews": 0})
    confirmed = sum(1 for review in reviews if review.status == "confirmed")
    status = "ready" if confirmed == len(reviews) else "attention"
    return _check("routing", status, round(confirmed / len(reviews) * 100), f"{confirmed}/{len(reviews)} routes confirmed.", {
        "reviews": len(reviews),
        "confirmed": confirmed,
    })


def _schema_check(proposals: list[SchemaProposal]) -> dict[str, Any]:
    if not proposals:
        return _check("schema", "pending", 0, "No schema proposal yet.", {"proposals": 0})
    approved = sum(1 for proposal in proposals if proposal.status == "approved")
    status = "ready" if approved else "attention"
    return _check("schema", status, 100 if approved else 55, f"{approved}/{len(proposals)} schemas approved.", {
        "proposals": len(proposals),
        "approved": approved,
    })


def _preview_check(plans: list[LoadPlan]) -> dict[str, Any]:
    if not plans:
        return _check("preview", "pending", 0, "No load preview yet.", {"plans": 0})
    plan = plans[0]
    rows = plan.preview_rows or []
    loadable = sum(1 for row in rows if row_is_loadable(row))
    errors = sum(1 for issue in plan.validation_issues or [] if issue.get("severity") == "error")
    status = "blocked" if plan.status == "blocked" or errors else "ready" if rows and loadable else "attention"
    score = 0 if not rows else round(loadable / len(rows) * 100)
    return _check("preview", status, score, f"{loadable}/{len(rows)} rows loadable.", {
        "rows": len(rows),
        "loadable": loadable,
        "errors": errors,
        "row_review": row_review_counts(rows),
    }, _issue_codes(plan))


def _source_check(db: Session, dataset_id: str, plans: list[LoadPlan]) -> dict[str, Any]:
    rows = [row for plan in plans for row in (plan.preview_rows or []) if isinstance(row, dict)]
    if not rows:
        return _check("source_references", "pending", 0, "No preview rows with sources yet.", {"rows": 0})
    issues = [issue for plan in plans for issue in source_reference_issues(db, dataset_id, plan.preview_rows or [])]
    invalid = sum(int(issue.get("count") or 1) for issue in issues)
    status = "ready" if not invalid else "blocked"
    return _check("source_references", status, round((len(rows) - invalid) / len(rows) * 100), f"{invalid} invalid source rows.", {
        "rows": len(rows),
        "invalid": invalid,
    }, [issue["code"] for issue in issues])


def _load_check(plans: list[LoadPlan]) -> dict[str, Any]:
    if not plans:
        return _check("load", "pending", 0, "No load plan yet.", {"plans": 0})
    loaded = [plan for plan in plans if plan.status == "loaded"]
    blocked = [plan for plan in plans if plan.status == "blocked"]
    status = "ready" if loaded else "blocked" if blocked else "attention"
    score = 100 if loaded else 20 if blocked else 55
    return _check("load", status, score, f"{len(loaded)}/{len(plans)} plans loaded.", {
        "plans": len(plans),
        "loaded": len(loaded),
        "blocked": len(blocked),
    }, [plan.id for plan in blocked[:8]])


def _retrieval_check(plans: list[LoadPlan]) -> dict[str, Any]:
    loaded = [plan for plan in plans if plan.status == "loaded"]
    if not loaded:
        return _check("retrieval", "pending", 0, "No loaded agent tables yet.", {"loaded_plans": 0})
    ready = [plan for plan in loaded if (plan.agent_preparation_json or {}).get("ready_for_agent")]
    status = "ready" if ready else "attention"
    return _check("retrieval", status, round(len(ready) / len(loaded) * 100), f"{len(ready)}/{len(loaded)} plans ready for agent.", {
        "loaded_plans": len(loaded),
        "ready": len(ready),
    })


def _golden_check(db: Session, dataset_id: str, rows: list[GoldenCheck], plans: list[LoadPlan]) -> dict[str, Any]:
    if not any(plan.status == "loaded" for plan in plans):
        return _check("golden_answers", "pending", 0, "No loaded agent data to evaluate yet.", {"checks": len(rows)})
    gate = dataset_golden_gate(db, dataset_id)
    latest = gate.get("latest_run") if isinstance(gate.get("latest_run"), dict) else {}
    score = int(latest.get("score") or (50 if gate["status"] == "pending" else 0))
    status = "ready" if gate["status"] == "passed" else "attention" if gate["status"] == "pending" else "blocked"
    return _check("golden_answers", status, score, f"Golden gate {gate['status']}.", {
        "checks": len(rows),
        "gate": gate,
    }, [str(item) for item in gate["reasons"][:8]])


def _golden_score(results: list[dict[str, Any]], fallback: int) -> int:
    scores = [int(result.get("score") or 0) for result in results]
    return round(mean(scores)) if scores else fallback


def _check(key: str, status: str, score: int, detail: str, metrics: dict[str, Any], blockers: list[Any] | None = None) -> dict[str, Any]:
    return {"key": key, "status": status, "score": max(0, min(100, score)), "detail": detail, "metrics": metrics, "blockers": blockers or []}


def _issue_codes(plan: LoadPlan) -> list[str]:
    return [str(issue.get("code")) for issue in plan.validation_issues or [] if issue.get("severity") == "error"][:8]


def _overall_score(checks: list[dict[str, Any]]) -> int:
    weights = {"ready": 1.0, "attention": 0.65, "pending": 0.0, "blocked": 0.15}
    return round(mean(int(check["score"]) * weights.get(str(check["status"]), 0) for check in checks))


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if all(check["status"] == "pending" for check in checks):
        return "pending"
    if any(check["status"] == "blocked" for check in checks):
        return "blocked"
    if all(check["status"] == "ready" for check in checks):
        return "ready"
    return "needs_attention"


def _blockers(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"key": check["key"], "blockers": check["blockers"]} for check in checks if check["blockers"]]


def _next_actions(checks: list[dict[str, Any]]) -> list[str]:
    keys = {"gemma_summary": "summary", "source_references": "preview", "load": "materialization", "golden_answers": "retrieval"}
    return [f"readiness_next_{keys.get(str(check['key']), str(check['key']))}" for check in checks if check["status"] != "ready"][:4]
