import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, or_, text
from sqlalchemy.orm import Session

from .connection_urls import connection_url
from .db import get_db
from .embeddings import embed_texts, vector_literal
from .models import DatabaseConnection, Dataset, Document, DocumentBlock, TableCatalog
from .search_fusion import rrf_fuse_hits
from .search_rerank import rerank_hits
from .schemas import SearchHit, SearchRequest

router = APIRouter()
STOPWORDS = {"what", "which", "where", "when", "with", "about", "что", "где", "как", "когда", "меня", "үшін"}


@router.post("/datasets/{dataset_id}/search", response_model=list[SearchHit])
def search_dataset(dataset_id: str, payload: SearchRequest, db: Session = Depends(get_db)) -> list[SearchHit]:
    _require_dataset(db, dataset_id)
    limit = max(1, min(payload.limit, 50))
    doc_ids = [row[0] for row in db.query(Document.id).filter(Document.dataset_id == dataset_id).all()]
    agent_hits = _agent_hits(db, doc_ids, payload.query, limit)
    raw_hits = _raw_hits(db, dataset_id, payload.query, limit)
    return rerank_hits(payload.query, rrf_fuse_hits(agent_hits + raw_hits, limit * 2), limit)


def _agent_hits(db: Session, document_ids: list[str], query: str, limit: int) -> list[SearchHit]:
    if not document_ids:
        return []
    vector, embedding_status = _query_vector(query)
    hits: list[SearchHit] = []
    catalogs = db.query(TableCatalog).order_by(TableCatalog.updated_at.desc()).limit(40).all()
    connections = {row.id: row for row in db.query(DatabaseConnection).all()}
    for catalog in catalogs:
        chunk_table = (catalog.agent_profile_json or {}).get("chunk_table")
        connection = connections.get(catalog.connection_id)
        if not chunk_table or not connection:
            continue
        hits.extend(_chunk_hits(connection, catalog.schema_name, str(chunk_table), document_ids, query, vector, limit))
        if len(hits) >= limit:
            break
    return rrf_fuse_hits(hits, limit, embedding_status=embedding_status)


def _chunk_hits(
    connection: DatabaseConnection,
    schema: str,
    table: str,
    document_ids: list[str],
    query: str,
    vector: list[float] | None,
    limit: int,
) -> list[SearchHit]:
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    params = {
        "query": query,
        "bm25_query": _bm25_query(query),
        "pattern": f"%{query}%",
        "patterns": _term_patterns(query),
        "doc_ids": document_ids,
        "limit": limit,
    }
    if vector:
        params["vector"] = vector_literal(vector)
    rows = []
    with engine.connect() as conn:
        rows.extend(_execute_chunk_sql(conn, _bm25_sql(schema, table), params))
        if vector:
            rows.extend(_execute_chunk_sql(conn, _vector_sql(schema, table), params))
        if len(rows) < limit:
            rows.extend(_execute_chunk_sql(conn, _fts_sql(schema, table), params))
    return [
        SearchHit(
            document_id=str(row["source_document_id"]),
            block_id=str(row["source_block_id"]),
            file_name=str(row["source_file"] or ""),
            block_type="agent_chunk",
            page=row["page"],
            sheet_name=row["sheet"],
            slide_number=None,
            text=str(row["content"])[:1600],
            score=float(row["score"] or 0.0),
            match_source=str(row["match_source"]),
            target_table=table.replace("_ai_chunks", ""),
            metadata={**(row.get("metadata") or {}), "source_confidence": row.get("confidence")},
        )
        for row in rows
    ]


def _execute_chunk_sql(conn: object, sql: str, params: dict) -> list:
    try:
        return conn.execute(text(sql), params).mappings().all()
    except Exception:
        return []


def _bm25_sql(schema: str, table: str) -> str:
    return f"""
        SELECT source_document_id, source_block_id, source_file, page, sheet, content,
               metadata, confidence,
               paradedb.score(id) AS bm25_score,
               (paradedb.score(id) + coalesce(confidence, 0)) AS score,
               'bm25' AS match_source
        FROM {_qi(schema)}.{_qi(table)}
        WHERE source_document_id = ANY(:doc_ids)
          AND content @@@ :bm25_query
        ORDER BY bm25_score DESC, confidence DESC
        LIMIT :limit
    """


def _vector_sql(schema: str, table: str) -> str:
    return f"""
        SELECT source_document_id, source_block_id, source_file, page, sheet, content,
               metadata, confidence,
               1 / (1 + (embedding <=> CAST(:vector AS vector))) AS vector_score,
               (1 / (1 + (embedding <=> CAST(:vector AS vector))) + coalesce(confidence, 0)) AS score,
               'semantic_vector' AS match_source
        FROM {_qi(schema)}.{_qi(table)}
        WHERE source_document_id = ANY(:doc_ids)
          AND embedding IS NOT NULL
        ORDER BY vector_score DESC, confidence DESC
        LIMIT :limit
    """


def _fts_sql(schema: str, table: str) -> str:
    return f"""
        WITH ranked AS (
          SELECT source_document_id, source_block_id, source_file, page, sheet, content,
                 metadata, confidence,
                 ts_rank(search_tsv, websearch_to_tsquery('simple', :query)) AS keyword_score
          FROM {_qi(schema)}.{_qi(table)}
          WHERE source_document_id = ANY(:doc_ids)
            AND (
              search_tsv @@ websearch_to_tsquery('simple', :query)
              OR content ILIKE :pattern
              OR content ILIKE ANY(:patterns)
            )
        )
        SELECT *, (keyword_score * 2 + coalesce(confidence, 0)) AS score,
               'fts_keyword' AS match_source
        FROM ranked
        ORDER BY score DESC
        LIMIT :limit
    """


def _raw_hits(db: Session, dataset_id: str, query: str, limit: int) -> list[SearchHit]:
    pattern = f"%{query}%"
    term_filters = []
    for item in _term_patterns(query):
        term_filters.extend([DocumentBlock.text.ilike(item), Document.file_name.ilike(item)])
    rows = (
        db.query(DocumentBlock, Document)
        .join(Document, Document.id == DocumentBlock.document_id)
        .filter(Document.dataset_id == dataset_id)
        .filter(or_(DocumentBlock.text.ilike(pattern), Document.file_name.ilike(pattern), *term_filters))
        .limit(limit)
        .all()
    )
    return [
        SearchHit(
            document_id=document.id,
            block_id=block.id,
            file_name=document.file_name,
            block_type=block.block_type,
            page=block.page,
            sheet_name=block.sheet_name,
            slide_number=block.slide_number,
            text=block.text[:1200],
            score=0.35,
            match_source="raw_block",
            target_table=None,
            metadata={"source_confidence": block.confidence},
        )
        for block, document in rows
    ]


def _query_vector(query: str) -> tuple[list[float] | None, str]:
    vectors, status = embed_texts([query])
    return (vectors[0] if vectors else None), status


def _term_patterns(query: str) -> list[str]:
    terms = []
    for term in re.findall(r"[0-9A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі_-]{3,}", query.lower()):
        if term not in STOPWORDS and term not in terms:
            terms.append(term)
    return [f"%{term}%" for term in terms[:8]] or [f"%{query}%"]


def _bm25_query(query: str) -> str:
    terms = [item.strip() for item in query.split() if item.strip()]
    return " ".join(terms) or query


def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
