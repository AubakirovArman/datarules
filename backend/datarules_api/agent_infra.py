import json
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .analysis_index import analysis_index_rows
from .connection_urls import connection_url
from .config import get_settings
from .embeddings import embed_texts, vector_literal
from .load_modes import is_analysis_only
from .materialization_verify import verify_materialization
from .models import DatabaseConnection, LoadPlan, TableCatalog
from .row_identity import stable_row_id
from .row_review import normalize_row_status, row_is_loadable
from .target_writer import write_target_rows
from .write_policy import connection_can_write


def materialize_load_plan(db: Session, plan: LoadPlan) -> dict[str, Any]:
    settings = get_settings()
    connection = _resolve_connection(db, plan.connection_id)
    schema = plan.schema_name or connection.default_schema
    if not connection_can_write(connection, schema):
        raise ValueError(f"Write access is not enabled for {connection.name} schema {schema}")
    analysis_only = is_analysis_only(plan.target_mode, plan.target_table)
    chunk_table = _chunk_table_name(plan.target_table)
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    inserted = 0
    inserted_records = 0
    bm25_ready = False
    embedding_status = "disabled"
    with engine.begin() as conn:
        _enable_extensions(conn)
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_qi(schema)}"))
        inserted_records = 0 if analysis_only else write_target_rows(conn, schema, plan)
        _create_chunk_table(conn, schema, chunk_table, settings.embedding_dimensions)
        bm25_ready = _create_indexes(conn, schema, chunk_table)
        rows = _index_rows(db, plan, analysis_only)
        chunk_ids = [stable_row_id(row) for row in rows]
        vectors, embedding_status = embed_texts([_row_content(row) for row in rows])
        for index, row in enumerate(rows):
            vector = vectors[index] if index < len(vectors) else None
            _insert_chunk(conn, schema, chunk_table, plan.target_table, row, vector)
            inserted += 1
        _purge_duplicate_chunks(conn, schema, chunk_table, plan.target_table, rows)
    with engine.begin() as conn:
        verification = verify_materialization(
            conn,
            schema,
            plan.target_table,
            chunk_table,
            chunk_ids,
            inserted_records,
            inserted,
            bm25_ready,
            embedding_status,
            target_required=not analysis_only,
        )
    semantic_ready = embedding_status == "ready" and inserted > 0
    _upsert_catalog(db, connection.id, schema, plan, chunk_table, inserted_records, inserted, bm25_ready, semantic_ready, analysis_only)
    return {
        "stage": "indexed" if analysis_only else "materialized",
        "target_mode": plan.target_mode,
        "analysis_only": analysis_only,
        "structured_table": not analysis_only,
        "ready_for_agent": semantic_ready or bm25_ready,
        "connection_id": connection.id,
        "schema_name": schema,
        "target_table": plan.target_table,
        "inserted_records": inserted_records,
        "chunk_table": chunk_table,
        "inserted_chunks": inserted,
        "embedding_model": settings.embedding_model_id,
        "embedding_status": embedding_status,
        "embedding_dimensions": settings.embedding_dimensions,
        "semantic_search": semantic_ready,
        "bm25": bm25_ready,
        "keyword_search": True,
        "verification": verification,
    }


def _enable_extensions(conn: Any) -> None:
    for extension in ("vector", "pg_search", "pg_trgm"):
        conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))


def _create_chunk_table(conn: Any, schema: str, table: str, dimensions: int) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_qi(schema)}.{_qi(table)} (
              id text PRIMARY KEY,
              target_table text NOT NULL,
              source_document_id text NOT NULL,
              source_block_id text NOT NULL,
              source_file text,
              page integer,
              sheet text,
              content text NOT NULL,
              metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
              confidence double precision,
              embedding vector({dimensions}),
              search_tsv tsvector GENERATED ALWAYS AS
                (to_tsvector('simple', coalesce(content, ''))) STORED,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


def _create_indexes(conn: Any, schema: str, table: str) -> bool:
    name = _index_prefix(schema, table)
    conn.execute(
        text(f"CREATE INDEX IF NOT EXISTS {_qi(name + '_fts')} ON {_qi(schema)}.{_qi(table)} USING gin(search_tsv)")
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS {_qi(name + '_vec')} "
            f"ON {_qi(schema)}.{_qi(table)} USING hnsw (embedding vector_cosine_ops)"
        )
    )
    try:
        conn.execute(text("SAVEPOINT datarules_bm25"))
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {_qi(name + '_bm25')} "
                f"ON {_qi(schema)}.{_qi(table)} USING bm25 (id, content) WITH (key_field='id')"
            )
        )
        conn.execute(text("RELEASE SAVEPOINT datarules_bm25"))
        return True
    except Exception:
        conn.execute(text("ROLLBACK TO SAVEPOINT datarules_bm25"))
        conn.execute(text("RELEASE SAVEPOINT datarules_bm25"))
        return False


def _insert_chunk(
    conn: Any,
    schema: str,
    table: str,
    target_table: str,
    row: dict[str, Any],
    vector: list[float] | None,
) -> None:
    conn.execute(
        text(
            f"""
            INSERT INTO {_qi(schema)}.{_qi(table)}
              (id, target_table, source_document_id, source_block_id, source_file, page, sheet, content, metadata, confidence, embedding)
            VALUES
              (:id, :target_table, :source_document_id, :source_block_id, :source_file, :page, :sheet, :content, CAST(:metadata AS jsonb), :confidence, CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET
              content = excluded.content,
              metadata = excluded.metadata,
              confidence = excluded.confidence,
              embedding = excluded.embedding
            """
        ),
        {
            "id": stable_row_id(row),
            "target_table": target_table,
            "source_document_id": row.get("source_document_id"),
            "source_block_id": row.get("source_block_id"),
            "source_file": row.get("source_file"),
            "page": row.get("page"),
            "sheet": row.get("sheet"),
            "content": _row_content(row),
            "metadata": json.dumps(
                {
                    "field_values": row.get("field_values", {}),
                    "field_sources": row.get("field_sources", {}),
                    "extraction_source": row.get("extraction_source"),
                    "row_status": normalize_row_status(row),
                    "validation_errors": row.get("validation_errors", []),
                },
                ensure_ascii=False,
            ),
            "confidence": row.get("confidence"),
            "embedding": vector_literal(vector),
        },
    )


def _purge_duplicate_chunks(conn: Any, schema: str, table: str, target_table: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conn.execute(
            text(
                f"""
                DELETE FROM {_qi(schema)}.{_qi(table)}
                WHERE target_table = :target_table
                  AND source_document_id = :source_document_id
                  AND source_block_id = :source_block_id
                  AND id <> :id
                """
            ),
            {
                "target_table": target_table,
                "source_document_id": row.get("source_document_id"),
                "source_block_id": row.get("source_block_id"),
                "id": stable_row_id(row),
            },
        )


def _upsert_catalog(
    db: Session,
    connection_id: str,
    schema: str,
    plan: LoadPlan,
    chunk_table: str,
    inserted_records: int,
    inserted: int,
    bm25_ready: bool,
    semantic_ready: bool,
    analysis_only: bool = False,
) -> None:
    row = (
        db.query(TableCatalog)
        .filter(TableCatalog.connection_id == connection_id)
        .filter(TableCatalog.schema_name == schema)
        .filter(TableCatalog.table_name == plan.target_table)
        .first()
    )
    if not row:
        row = TableCatalog(connection_id=connection_id, schema_name=schema, table_name=plan.target_table)
        db.add(row)
    row.description = row.description or ("DataRules analysis-only search index." if analysis_only else "DataRules approved destination table.")
    row.agent_profile_json = {
        "analysis_only": analysis_only,
        "target_mode": plan.target_mode,
        "chunk_table": chunk_table,
        "inserted_records": inserted_records,
        "inserted_chunks": inserted,
        "semantic_search": semantic_ready,
        "bm25": bm25_ready,
        "source_references_required": True,
    }
    row.updated_at = datetime.utcnow()
    db.flush()


def _resolve_connection(db: Session, connection_id: str | None) -> DatabaseConnection:
    if connection_id:
        connection = db.get(DatabaseConnection, connection_id)
    else:
        connection = db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()
    if not connection:
        raise ValueError("Database connection is not configured")
    return connection


def _index_rows(db: Session, plan: LoadPlan, analysis_only: bool) -> list[dict[str, Any]]:
    if analysis_only:
        return [row for row in analysis_index_rows(db, plan) if _row_content(row)]
    return [row for row in plan.preview_rows if row_is_loadable(row) and _row_content(row)]


def _chunk_table_name(table: str) -> str:
    return f"{table[:45]}_ai_chunks"


def _row_content(row: dict[str, Any]) -> str:
    return str(row.get("content") or row.get("field_text") or "")


def _index_prefix(schema: str, table: str) -> str:
    return f"idx_{schema[:20]}_{table[:35]}".replace("-", "_")


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
