from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .connection_urls import connection_url
from .db_probe import checked_engine, connection_failure_message
from .models import DatabaseConnection, TableCatalog
from .write_policy import connection_can_write


def purge_document_materialization(db: Session, document_id: str) -> dict[str, Any]:
    connections = {row.id: row for row in db.query(DatabaseConnection).all()}
    totals = {"target_rows": 0, "chunk_rows": 0, "tables_checked": 0, "tables_skipped": 0}
    details = []
    for catalog in db.query(TableCatalog).all():
        connection = connections.get(catalog.connection_id)
        result = _purge_catalog(connection, catalog, document_id)
        details.append(result)
        totals["target_rows"] += int(result.get("target_rows", 0))
        totals["chunk_rows"] += int(result.get("chunk_rows", 0))
        if result["status"] == "skipped":
            totals["tables_skipped"] += 1
        else:
            totals["tables_checked"] += 1
    return {**totals, "details": details}


def _purge_catalog(
    connection: DatabaseConnection | None,
    catalog: TableCatalog,
    document_id: str,
) -> dict[str, Any]:
    base = {
        "connection_id": catalog.connection_id,
        "schema": catalog.schema_name,
        "target_table": catalog.table_name,
        "chunk_table": (catalog.agent_profile_json or {}).get("chunk_table"),
    }
    if not connection:
        return {**base, "status": "skipped", "reason": "missing_connection"}
    if not connection_can_write(connection, catalog.schema_name):
        return {**base, "status": "skipped", "reason": "write_not_allowed"}
    url = connection_url(connection)
    try:
        engine = checked_engine(url)
        with engine.begin() as conn:
            target_rows = _delete_from_table(conn, catalog.schema_name, catalog.table_name, document_id)
            chunk_table = (catalog.agent_profile_json or {}).get("chunk_table")
            chunk_rows = _delete_from_table(conn, catalog.schema_name, str(chunk_table), document_id) if chunk_table else 0
        return {**base, "status": "purged", "target_rows": target_rows, "chunk_rows": chunk_rows}
    except Exception as exc:
        return {**base, "status": "skipped", "reason": connection_failure_message(exc, url)}


def _delete_from_table(conn: Any, schema: str, table: str, document_id: str) -> int:
    if not table or not _has_column(conn, schema, table, "source_document_id"):
        return 0
    result = conn.execute(
        text(f"DELETE FROM {_qi(schema)}.{_qi(table)} WHERE source_document_id = :document_id"),
        {"document_id": document_id},
    )
    return int(result.rowcount or 0)


def _has_column(conn: Any, schema: str, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table AND column_name = :column
                """
            ),
            {"schema": schema, "table": table, "column": column},
        ).first()
    )


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
