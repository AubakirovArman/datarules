from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from .answering import ANSWER_PROMPT_VERSION
from .config import get_settings
from .models import Document, DocumentBlock, LoadPlan, SchemaVersion


def evaluation_snapshot(db: Session, dataset_id: str, golden_checks: int) -> dict[str, Any]:
    settings = get_settings()
    plans = _plans(db, dataset_id)
    loaded = [plan for plan in plans if plan.status == "loaded"]
    ready = [plan for plan in loaded if _ready_for_agent(plan)]
    latest_schema = _latest_schema(db, dataset_id)
    return {
        "created_at": datetime.utcnow().isoformat(),
        "answer_prompt_version": ANSWER_PROMPT_VERSION,
        "gemma_model_id": settings.gemma_model_id,
        "gemma_base_url": settings.gemma_base_url or "",
        "gemma_gpu_id": settings.gemma_gpu_id,
        "embedding_model_id": settings.embedding_model_id,
        "embedding_base_url": settings.embedding_base_url or "",
        "embedding_dimensions": settings.embedding_dimensions,
        "keyword_search_engine": settings.keyword_search_engine,
        "documents": _document_count(db, dataset_id),
        "document_blocks": _block_count(db, dataset_id),
        "golden_checks": golden_checks,
        "load_plans": len(plans),
        "loaded_plans": len(loaded),
        "ready_agent_tables": len(ready),
        "semantic_tables": _agent_flag_count(ready, "semantic_search"),
        "bm25_tables": _agent_flag_count(ready, "bm25"),
        "latest_load_plan_id": plans[0].id if plans else None,
        "latest_schema_version_id": latest_schema.id if latest_schema else None,
        "ready_tables": [_ready_table(plan) for plan in ready[:8]],
    }


def _plans(db: Session, dataset_id: str) -> list[LoadPlan]:
    return (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id)
        .order_by(LoadPlan.updated_at.desc(), LoadPlan.created_at.desc())
        .all()
    )


def _latest_schema(db: Session, dataset_id: str) -> SchemaVersion | None:
    return (
        db.query(SchemaVersion)
        .filter(SchemaVersion.dataset_id == dataset_id)
        .order_by(SchemaVersion.created_at.desc())
        .first()
    )


def _document_count(db: Session, dataset_id: str) -> int:
    return int(db.query(func.count(Document.id)).filter(Document.dataset_id == dataset_id).scalar() or 0)


def _block_count(db: Session, dataset_id: str) -> int:
    return int(
        db.query(func.count(DocumentBlock.id))
        .join(Document, DocumentBlock.document_id == Document.id)
        .filter(Document.dataset_id == dataset_id)
        .scalar()
        or 0
    )


def _ready_for_agent(plan: LoadPlan) -> bool:
    agent = plan.agent_preparation_json or {}
    indexes = agent.get("indexes") if isinstance(agent.get("indexes"), dict) else {}
    return bool(agent.get("ready_for_agent") or agent.get("keyword_search") or indexes.get("full_text"))


def _agent_flag_count(plans: list[LoadPlan], flag: str) -> int:
    return sum(1 for plan in plans if (plan.agent_preparation_json or {}).get(flag))


def _ready_table(plan: LoadPlan) -> dict[str, Any]:
    agent = plan.agent_preparation_json or {}
    return {
        "plan_id": plan.id,
        "table": f"{plan.schema_name}.{plan.target_table}",
        "chunk_table": agent.get("chunk_table"),
        "inserted_chunks": int(agent.get("inserted_chunks") or 0),
        "semantic_search": bool(agent.get("semantic_search")),
        "bm25": bool(agent.get("bm25") or agent.get("keyword_search")),
    }
