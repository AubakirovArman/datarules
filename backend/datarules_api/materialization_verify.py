from typing import Any

from sqlalchemy import text


def verify_materialization(
    conn: Any,
    schema: str,
    target_table: str,
    chunk_table: str,
    chunk_ids: list[str],
    inserted_records: int,
    inserted_chunks: int,
    bm25_expected: bool,
    embedding_status: str,
    target_required: bool = True,
) -> dict[str, Any]:
    target_exists = _table_exists(conn, schema, target_table) if target_required else False
    chunk_exists = _table_exists(conn, schema, chunk_table)
    index_names = _index_names(conn, schema, chunk_table) if chunk_exists else []
    target_rows = _target_rows(conn, schema, target_table) if target_exists else 0
    source_rows = _source_rows(conn, schema, target_table) if target_exists else 0
    chunk_rows = _chunk_rows(conn, schema, chunk_table, chunk_ids) if chunk_exists else 0
    embedding_rows = _embedding_rows(conn, schema, chunk_table, chunk_ids) if chunk_exists else 0
    checks = _checks(
        target_exists,
        chunk_exists,
        inserted_records,
        inserted_chunks,
        chunk_rows,
        embedding_rows,
        index_names,
        bm25_expected,
        embedding_status,
        target_required,
    )
    return {
        "status": "ready" if all(item["ok"] for item in checks if item["critical"]) else "needs_attention",
        "checks": checks,
        "target_table": {
            "name": f"{schema}.{target_table}",
            "exists": target_exists,
            "total_rows": target_rows,
            "rows_with_source_refs": source_rows,
            "inserted_records": inserted_records,
            "required": target_required,
        },
        "chunk_table": {
            "name": f"{schema}.{chunk_table}",
            "exists": chunk_exists,
            "rows_for_plan": chunk_rows,
            "inserted_chunks": inserted_chunks,
        },
        "indexes": {
            "names": index_names,
            "full_text": any(name.endswith("_fts") for name in index_names),
            "vector": any(name.endswith("_vec") for name in index_names),
            "bm25": any(name.endswith("_bm25") for name in index_names),
        },
        "embeddings": {
            "status": embedding_status,
            "rows_with_embedding": embedding_rows,
            "expected_rows": inserted_chunks,
        },
    }


def _checks(
    target_exists: bool,
    chunk_exists: bool,
    inserted_records: int,
    inserted_chunks: int,
    chunk_rows: int,
    embedding_rows: int,
    index_names: list[str],
    bm25_expected: bool,
    embedding_status: str,
    target_required: bool,
) -> list[dict[str, Any]]:
    fts = any(name.endswith("_fts") for name in index_names)
    vector = any(name.endswith("_vec") for name in index_names)
    bm25 = any(name.endswith("_bm25") for name in index_names)
    embedding_ok = embedding_status != "ready" or embedding_rows >= inserted_chunks
    target_checks = [
        {"code": "target_table_exists", "ok": target_exists, "critical": True},
        {"code": "target_records_written", "ok": inserted_records > 0, "critical": True},
    ] if target_required else [{"code": "analysis_only_index", "ok": True, "critical": False}]
    return [
        *target_checks,
        {"code": "chunk_table_exists", "ok": chunk_exists, "critical": True},
        {"code": "chunks_written", "ok": chunk_rows >= inserted_chunks > 0, "critical": True},
        {"code": "full_text_index", "ok": fts, "critical": True},
        {"code": "vector_index", "ok": vector, "critical": False},
        {"code": "bm25_index", "ok": bm25 or not bm25_expected, "critical": False},
        {"code": "embeddings_written", "ok": embedding_ok, "critical": embedding_status == "ready"},
    ]


def _table_exists(conn: Any, schema: str, table: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :table
                """
            ),
            {"schema": schema, "table": table},
        ).first()
    )


def _index_names(conn: Any, schema: str, table: str) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = :schema AND tablename = :table
            ORDER BY indexname
            """
        ),
        {"schema": schema, "table": table},
    )
    return [str(row[0]) for row in rows]


def _target_rows(conn: Any, schema: str, table: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {_qi(schema)}.{_qi(table)}")).scalar() or 0)


def _source_rows(conn: Any, schema: str, table: str) -> int:
    return int(
        conn.execute(
            text(
                f"""
                SELECT count(*) FROM {_qi(schema)}.{_qi(table)}
                WHERE source_document_id IS NOT NULL AND source_block_id IS NOT NULL
                """
            )
        ).scalar()
        or 0
    )


def _chunk_rows(conn: Any, schema: str, table: str, chunk_ids: list[str]) -> int:
    if not chunk_ids:
        return 0
    return int(
        conn.execute(
            text(f"SELECT count(*) FROM {_qi(schema)}.{_qi(table)} WHERE id = ANY(:chunk_ids)"),
            {"chunk_ids": chunk_ids},
        ).scalar()
        or 0
    )


def _embedding_rows(conn: Any, schema: str, table: str, chunk_ids: list[str]) -> int:
    if not chunk_ids:
        return 0
    return int(
        conn.execute(
            text(
                f"""
                SELECT count(*) FROM {_qi(schema)}.{_qi(table)}
                WHERE id = ANY(:chunk_ids) AND embedding IS NOT NULL
                """
            ),
            {"chunk_ids": chunk_ids},
        ).scalar()
        or 0
    )


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
