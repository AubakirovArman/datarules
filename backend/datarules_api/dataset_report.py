from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .document_quality import build_quality_profile
from .models import Dataset, Document, DocumentAiSummary, DocumentBlock, DocumentReview, LoadPlan, SchemaProposal
from .row_review import row_is_loadable, row_review_counts

router = APIRouter()


@router.get("/datasets/{dataset_id}/report")
def dataset_report(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    documents = db.query(Document).filter(Document.dataset_id == dataset_id).order_by(Document.created_at).all()
    doc_ids = [document.id for document in documents]
    blocks_by_doc = _blocks_by_doc(db, doc_ids)
    summaries = _summaries_by_doc(db, doc_ids)
    reviews = db.query(DocumentReview).filter(DocumentReview.dataset_id == dataset_id).all()
    proposals = db.query(SchemaProposal).filter(SchemaProposal.dataset_id == dataset_id).all()
    plans = (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id)
        .order_by(LoadPlan.updated_at.desc(), LoadPlan.created_at.desc())
        .all()
    )
    review_by_doc = {review.document_id: review for review in reviews}
    return {
        "dataset": _dataset(dataset),
        "status": _status(documents, reviews, proposals, plans),
        "counts": _counts(documents, blocks_by_doc, summaries, reviews, proposals, plans),
        "documents": [_document(document, blocks_by_doc[document.id], summaries.get(document.id), review_by_doc.get(document.id)) for document in documents],
        "routing": _routing(reviews),
        "schemas": _schemas(proposals),
        "loading": _loading(plans),
        "retrieval": _retrieval(plans),
        "warnings": _warnings(documents, blocks_by_doc, reviews, plans),
        "next_actions": _next_actions(documents, summaries, reviews, proposals, plans),
    }


def _blocks_by_doc(db: Session, doc_ids: list[str]) -> dict[str, list[DocumentBlock]]:
    grouped: dict[str, list[DocumentBlock]] = defaultdict(list)
    if not doc_ids:
        return grouped
    rows = db.query(DocumentBlock).filter(DocumentBlock.document_id.in_(doc_ids)).order_by(DocumentBlock.page).all()
    for block in rows:
        grouped[block.document_id].append(block)
    return grouped


def _summaries_by_doc(db: Session, doc_ids: list[str]) -> dict[str, DocumentAiSummary]:
    if not doc_ids:
        return {}
    rows = (
        db.query(DocumentAiSummary)
        .filter(DocumentAiSummary.document_id.in_(doc_ids))
        .order_by(DocumentAiSummary.updated_at.desc())
        .all()
    )
    result: dict[str, DocumentAiSummary] = {}
    for row in rows:
        result.setdefault(row.document_id, row)
    return result


def _dataset(dataset: Dataset) -> dict[str, Any]:
    return {"id": dataset.id, "name": dataset.name, "description": dataset.description, "status": dataset.status}


def _document(document: Document, blocks: list[DocumentBlock], summary: DocumentAiSummary | None, review: DocumentReview | None) -> dict[str, Any]:
    counts = Counter(block.block_type for block in blocks)
    ai = summary.summary_json if summary else {}
    pages = sorted({block.page for block in blocks if block.page is not None})
    sheets = sorted({block.sheet_name for block in blocks if block.sheet_name})
    slides = sorted({block.slide_number for block in blocks if block.slide_number is not None})
    return {
        "id": document.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "status": document.status,
        "summary": str(ai.get("summary") or _fallback_summary(document, blocks)),
        "summary_source": str(ai.get("source") or "deterministic"),
        "key_points": _list(ai.get("key_points"), 5),
        "entities": _list(ai.get("entities"), 6),
        "metrics": {
            "blocks": len(blocks),
            "pages": len(pages),
            "sheets": len(sheets),
            "slides": len(slides),
            "tables": counts["table"],
            "text_chars": sum(len(block.text or "") for block in blocks),
        },
        "quality": build_quality_profile(blocks),
        "route": _route(review),
        "canonical_json": f"/datasets/{document.dataset_id}/files/{document.id}/canonical",
    }


def _route(review: DocumentReview | None) -> dict[str, Any]:
    if not review:
        return {"status": "missing"}
    return {
        "status": review.status,
        "selected_doc_type": review.selected_doc_type,
        "selected_table": review.selected_table,
        "recommended_doc_type": _option(review.doc_type_options),
        "recommended_table": _option(review.table_options),
        "reason": review.reason,
    }


def _option(options: Any) -> dict[str, Any] | None:
    if isinstance(options, list) and options and isinstance(options[0], dict):
        return options[0]
    return None


def _counts(
    documents: list[Document],
    blocks_by_doc: dict[str, list[DocumentBlock]],
    summaries: dict[str, DocumentAiSummary],
    reviews: list[DocumentReview],
    proposals: list[SchemaProposal],
    plans: list[LoadPlan],
) -> dict[str, int]:
    return {
        "documents": len(documents),
        "blocks": sum(len(blocks) for blocks in blocks_by_doc.values()),
        "ai_summaries": len(summaries),
        "routes_confirmed": sum(1 for review in reviews if review.status == "confirmed"),
        "routes_pending": sum(1 for review in reviews if review.status != "confirmed"),
        "schema_proposals": len(proposals),
        "schema_approved": sum(1 for proposal in proposals if proposal.status == "approved"),
        "load_plans": len(plans),
        "loaded_plans": sum(1 for plan in plans if plan.status == "loaded"),
    }


def _routing(reviews: list[DocumentReview]) -> dict[str, Any]:
    targets = Counter(review.selected_table or _option_value(review.table_options) or "unselected" for review in reviews)
    return {"total": len(reviews), "confirmed": sum(1 for review in reviews if review.status == "confirmed"), "targets": dict(targets)}


def _schemas(proposals: list[SchemaProposal]) -> list[dict[str, Any]]:
    return [{"id": proposal.id, "status": proposal.status, "tables": _proposal_tables(proposal.proposal_json)} for proposal in proposals]


def _loading(plans: list[LoadPlan]) -> list[dict[str, Any]]:
    return [
        {
            "id": plan.id,
            "status": plan.status,
            "destination": f"{plan.schema_name}.{plan.target_table}",
            "target_mode": plan.target_mode,
            "rows": len(plan.preview_rows or []),
            "loadable_rows": sum(1 for row in plan.preview_rows or [] if row_is_loadable(row)),
            "row_review": row_review_counts(plan.preview_rows or []),
            "issues": plan.validation_issues or [],
            "agent": plan.agent_preparation_json or {},
        }
        for plan in plans
    ]


def _retrieval(plans: list[LoadPlan]) -> dict[str, Any]:
    tables = []
    for plan in plans:
        agent = plan.agent_preparation_json or {}
        if plan.status != "loaded" and agent.get("stage") != "materialized":
            continue
        tables.append({
            "plan_id": plan.id,
            "table": f"{plan.schema_name}.{plan.target_table}",
            "chunk_table": agent.get("chunk_table"),
            "inserted_chunks": agent.get("inserted_chunks", 0),
            "semantic_search": bool(agent.get("semantic_search")),
            "keyword_search": bool(agent.get("keyword_search") or agent.get("bm25")),
            "bm25": bool(agent.get("bm25")),
            "ready_for_agent": bool(agent.get("ready_for_agent") or agent.get("keyword_search")),
        })
    return {"ready": any(table["ready_for_agent"] for table in tables), "tables": tables}


def _status(
    documents: list[Document],
    reviews: list[DocumentReview],
    proposals: list[SchemaProposal],
    plans: list[LoadPlan],
) -> str:
    if not documents:
        return "empty"
    if any(document.status not in {"extracted", "needs_review"} for document in documents):
        return "needs_extraction"
    if any(review.status != "confirmed" for review in reviews):
        return "needs_routing"
    if not proposals:
        return "needs_schema"
    if any(plan.status == "blocked" for plan in plans):
        return "blocked"
    if _retrieval(plans)["ready"]:
        return "ready_for_agent"
    if any(plan.status == "loaded" for plan in plans):
        return "loaded"
    if plans:
        return "needs_load_confirmation"
    return "needs_load_plan"


def _warnings(
    documents: list[Document],
    blocks_by_doc: dict[str, list[DocumentBlock]],
    reviews: list[DocumentReview],
    plans: list[LoadPlan],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not documents:
        warnings.append({"code": "no_documents", "severity": "warning"})
    for document in documents:
        blocks = blocks_by_doc[document.id]
        quality = build_quality_profile(blocks)
        if quality["status"] != "ready":
            warnings.append({
                "code": "document_quality",
                "severity": "warning",
                "document_id": document.id,
                "score": quality["extraction_score"],
            })
    pending = [review.document_id for review in reviews if review.status != "confirmed"]
    if pending:
        warnings.append({"code": "unconfirmed_routes", "severity": "warning", "document_ids": pending})
    for plan in plans:
        if plan.validation_issues:
            warnings.append({"code": "load_plan_issues", "severity": "warning", "plan_id": plan.id, "count": len(plan.validation_issues)})
    return warnings[:12]


def _next_actions(
    documents: list[Document],
    summaries: dict[str, DocumentAiSummary],
    reviews: list[DocumentReview],
    proposals: list[SchemaProposal],
    plans: list[LoadPlan],
) -> list[str]:
    actions = []
    if not documents:
        actions.append("readiness_next_upload")
    if documents and any(document.status not in {"extracted", "needs_review"} for document in documents):
        actions.append("readiness_next_extraction")
    if documents and len(summaries) < len(documents):
        actions.append("readiness_next_summary")
    if reviews and any(review.status != "confirmed" for review in reviews):
        actions.append("readiness_next_routing")
    if documents and not proposals:
        actions.append("readiness_next_schema")
    if proposals and not plans:
        actions.append("readiness_next_preview")
    if plans and not any(plan.status == "loaded" for plan in plans):
        actions.append("readiness_next_materialization")
    if any(plan.status == "loaded" for plan in plans) and not _retrieval(plans)["ready"]:
        actions.append("readiness_next_retrieval")
    return actions[:5]


def _fallback_summary(document: Document, blocks: list[DocumentBlock]) -> str:
    text = " ".join((block.text or "").strip() for block in blocks if block.text).strip()
    if text:
        return text[:420]
    return f"{document.file_name}: {len(blocks)} extracted blocks."


def _list(value: Any, limit: int) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _option_value(options: Any) -> str | None:
    option = _option(options)
    return str(option.get("value")) if option and option.get("value") else None


def _proposal_tables(value: dict[str, Any]) -> list[str]:
    tables = value.get("tables") if isinstance(value, dict) else []
    if isinstance(tables, list):
        return [str(table.get("name") or table.get("table_name") or table) for table in tables[:8]]
    table_name = value.get("table_name") if isinstance(value, dict) else None
    return [str(table_name)] if table_name else []
