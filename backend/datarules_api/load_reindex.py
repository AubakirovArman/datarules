from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .agent_infra import (
    _chunk_table_name,
    _create_chunk_table,
    _create_indexes,
    _enable_extensions,
    _insert_chunk,
    _resolve_connection,
    _row_content,
    _upsert_catalog,
    _qi,
)
from .analysis_index import analysis_index_rows
from .audit import record_audit_event
from .config import get_settings
from .connection_urls import connection_url
from .embeddings import embed_texts
from .db import get_db
from .load_modes import is_analysis_only
from .load_audit import load_event_payload, record_load_event
from .materialization_verify import verify_materialization
from .models import LoadPlan
from .row_identity import stable_row_id
from .row_review import row_is_loadable
from .schemas import LoadPlanOut

router = APIRouter()


@router.post("/load-plans/{plan_id}/reindex", response_model=LoadPlanOut)
def reindex_load_plan(plan_id: str, db: Session = Depends(get_db)) -> LoadPlan:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    if plan.status != "loaded":
        raise HTTPException(400, "Only loaded plans can be reindexed.")
    result = _reindex(db, plan)
    plan.agent_preparation_json = result
    plan.updated_at = datetime.utcnow()
    record_load_event(db, plan, "agent_reindexed", "Agent chunks, embeddings, and search indexes rebuilt.", load_event_payload(plan, {"agent_preparation": result}))
    record_audit_event(db, "load_plan.agent_reindexed", "load_plan", plan.id, plan.dataset_id, load_event_payload(plan, {"agent_preparation": result}))
    db.commit()
    db.refresh(plan)
    return plan


def _reindex(db: Session, plan: LoadPlan) -> dict[str, Any]:
    settings = get_settings()
    connection = _resolve_connection(db, plan.connection_id)
    schema = plan.schema_name or connection.default_schema
    chunk_table = _chunk_table_name(plan.target_table)
    rows = [row for row in analysis_index_rows(db, plan) if _row_content(row)] if is_analysis_only(plan.target_mode, plan.target_table) else [row for row in plan.preview_rows or [] if row_is_loadable(row) and _row_content(row)]
    chunk_ids = [stable_row_id(row) for row in rows]
    vectors, embedding_status = embed_texts([_row_content(row) for row in rows])
    bm25_ready = False
    analysis_only = is_analysis_only(plan.target_mode, plan.target_table)
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    with engine.begin() as conn:
        _enable_extensions(conn)
        _create_chunk_table(conn, schema, chunk_table, settings.embedding_dimensions)
        bm25_ready = _create_indexes(conn, schema, chunk_table)
        _delete_stale_chunks(conn, schema, chunk_table, plan.target_table, rows, chunk_ids)
        for index, row in enumerate(rows):
            vector = vectors[index] if index < len(vectors) else None
            _insert_chunk(conn, schema, chunk_table, plan.target_table, row, vector)
    inserted_records = int((plan.agent_preparation_json or {}).get("inserted_records") or len(rows))
    with engine.begin() as conn:
        verification = verify_materialization(
            conn,
            schema,
            plan.target_table,
            chunk_table,
            chunk_ids,
            inserted_records,
            len(rows),
            bm25_ready,
            embedding_status,
            target_required=not analysis_only,
        )
    semantic_ready = embedding_status == "ready" and bool(rows)
    _upsert_catalog(db, connection.id, schema, plan, chunk_table, inserted_records, len(rows), bm25_ready, semantic_ready, analysis_only)
    return _agent_payload(plan, schema, chunk_table, inserted_records, len(rows), embedding_status, bm25_ready, semantic_ready, verification)


def _delete_stale_chunks(conn: Any, schema: str, table: str, target_table: str, rows: list[dict[str, Any]], chunk_ids: list[str]) -> None:
    document_ids = sorted({str(row.get("source_document_id")) for row in rows if row.get("source_document_id")})
    if not document_ids:
        return
    conn.execute(
        text(
            f"""
            DELETE FROM {_qi(schema)}.{_qi(table)}
            WHERE target_table = :target_table
              AND source_document_id = ANY(:document_ids)
              AND NOT (id = ANY(:chunk_ids))
            """
        ),
        {"target_table": target_table, "document_ids": document_ids, "chunk_ids": chunk_ids},
    )


def _agent_payload(
    plan: LoadPlan,
    schema: str,
    chunk_table: str,
    inserted_records: int,
    inserted_chunks: int,
    embedding_status: str,
    bm25_ready: bool,
    semantic_ready: bool,
    verification: dict[str, Any],
) -> dict[str, Any]:
    current = plan.agent_preparation_json or {}
    return {
        **current,
        "stage": "indexed" if is_analysis_only(plan.target_mode, plan.target_table) else "materialized",
        "last_action": "reindexed",
        "target_mode": plan.target_mode,
        "analysis_only": is_analysis_only(plan.target_mode, plan.target_table),
        "structured_table": not is_analysis_only(plan.target_mode, plan.target_table),
        "last_reindexed_at": datetime.utcnow().isoformat(),
        "reindex_count": int(current.get("reindex_count") or 0) + 1,
        "ready_for_agent": semantic_ready or bm25_ready,
        "schema_name": schema,
        "target_table": plan.target_table,
        "inserted_records": inserted_records,
        "chunk_table": chunk_table,
        "inserted_chunks": inserted_chunks,
        "embedding_model": get_settings().embedding_model_id,
        "embedding_status": embedding_status,
        "embedding_dimensions": get_settings().embedding_dimensions,
        "semantic_search": semantic_ready,
        "bm25": bm25_ready,
        "keyword_search": True,
        "verification": verification,
    }
