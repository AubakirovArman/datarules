from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .connection_urls import connection_url, set_connection_url
from .db import get_db
from .db_connection_security import mark_connection_status
from .db_probe import checked_engine, connection_failure_message, database_capabilities
from .models import DatabaseConnection, TableCatalog
from .schemas import DatabaseConnectionCreate, DatabaseConnectionOut, DbIntrospectionOut, TableCatalogOut, TableCatalogUpsert
from .write_policy import write_policy
from .write_policy_guard import requested_schemas, validate_connection_default_schema, validate_write_policy_request
from .secret_store import secret_key_status
from .table_catalog_guard import table_catalog_error

router = APIRouter()
SYSTEM_SCHEMAS = {"information_schema", "paradedb", "pdb", "tiger", "topology"}
INTERNAL_TABLES = {
    "database_connections",
    "datasets",
    "document_blocks",
    "document_reviews",
    "documents",
    "ingestion_jobs",
    "job_events",
    "load_plans",
    "schema_proposals",
    "schema_versions",
    "spatial_ref_sys",
    "table_catalogs",
}


@router.get("/database-connections", response_model=list[DatabaseConnectionOut])
def list_connections(db: Session = Depends(get_db)) -> list[DatabaseConnection]:
    return db.query(DatabaseConnection).order_by(DatabaseConnection.created_at.desc()).all()


@router.post("/database-connections", response_model=DatabaseConnectionOut)
def create_connection(
    payload: DatabaseConnectionCreate,
    db: Session = Depends(get_db),
) -> DatabaseConnection:
    validate_connection_default_schema(payload.default_schema)
    engine = _new_engine_or_400(payload.sqlalchemy_url)
    capabilities = {
        **database_capabilities(engine),
        "secret_storage": secret_key_status(),
        "write_policy": write_policy(False, [payload.default_schema], "External connections are read-only until enabled."),
    }
    capabilities = mark_connection_status(capabilities, payload.sqlalchemy_url, "ok", "Connection created and tested.")
    connection = DatabaseConnection(
        name=payload.name,
        description=payload.description,
        default_schema=payload.default_schema,
        capabilities_json=capabilities,
    )
    set_connection_url(connection, payload.sqlalchemy_url, encrypt=True)
    db.add(connection)
    db.flush()
    record_audit_event(
        db,
        "database_connection.created",
        "database_connection",
        connection.id,
        payload={"name": connection.name, "schema": connection.default_schema, "capabilities": capabilities},
    )
    db.commit()
    db.refresh(connection)
    return connection


@router.post("/database-connections/{connection_id}/test")
def test_connection(connection_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    connection = _connection(db, connection_id)
    url, engine = _connection_engine_or_400(db, connection, "database_connection.test_failed")
    capabilities = database_capabilities(engine)
    connection.capabilities_json = mark_connection_status(
        {**(connection.capabilities_json or {}), **capabilities, "secret_storage": secret_key_status()},
        url,
        "ok",
        "Connection test succeeded.",
    )
    connection.updated_at = datetime.utcnow()
    record_audit_event(
        db,
        "database_connection.tested",
        "database_connection",
        connection.id,
        payload={"status": "ok", "capabilities": connection.capabilities_json},
    )
    db.commit()
    return {"status": "ok", "capabilities": connection.capabilities_json}


@router.post("/database-connections/{connection_id}/introspect", response_model=DbIntrospectionOut)
def introspect_connection(connection_id: str, db: Session = Depends(get_db)) -> DbIntrospectionOut:
    connection = _connection(db, connection_id)
    url, engine = _connection_engine_or_400(db, connection, "database_connection.introspection_failed")
    inspector = inspect(engine)
    schemas = [schema for schema in inspector.get_schema_names() if _is_user_schema(schema)]
    rows: list[TableCatalog] = []
    for schema in schemas:
        for table in inspector.get_table_names(schema=schema):
            if table in INTERNAL_TABLES:
                continue
            rows.append(_upsert_catalog(db, connection.id, schema, table, inspector))
    capabilities = {
        **database_capabilities(engine),
        "write_policy": (connection.capabilities_json or {}).get("write_policy")
        or write_policy(connection.is_internal, ["*"] if connection.is_internal else [connection.default_schema]),
    }
    capabilities = {**capabilities, "secret_storage": secret_key_status()}
    capabilities = mark_connection_status(capabilities, url, "ok", "Introspection succeeded.")
    connection.capabilities_json = capabilities
    connection.updated_at = datetime.utcnow()
    record_audit_event(
        db,
        "database_connection.introspected",
        "database_connection",
        connection.id,
        payload={"schemas": schemas, "table_count": len(rows), "capabilities": capabilities},
    )
    db.commit()
    return DbIntrospectionOut(
        connection_id=connection.id,
        schemas=schemas,
        tables=[TableCatalogOut.model_validate(row) for row in rows],
        capabilities=capabilities,
    )


@router.patch("/database-connections/{connection_id}/write-policy", response_model=DatabaseConnectionOut)
def update_write_policy(
    connection_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> DatabaseConnection:
    connection = _connection(db, connection_id)
    enabled = bool(payload.get("enabled"))
    schemas = requested_schemas(payload.get("schemas"), connection.default_schema)
    validate_write_policy_request(connection, enabled, schemas, payload)
    if connection.is_internal:
        enabled, schemas = True, ["*"]
    connection.capabilities_json = {
        **(connection.capabilities_json or {}),
        "write_policy": write_policy(enabled, schemas, "User-managed DataRules write policy."),
    }
    connection.updated_at = datetime.utcnow()
    record_audit_event(
        db,
        "database_connection.write_policy_updated",
        "database_connection",
        connection.id,
        payload={"enabled": enabled, "schemas": schemas, "is_internal": connection.is_internal},
    )
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/table-catalog", response_model=list[TableCatalogOut])
def list_table_catalog(db: Session = Depends(get_db)) -> list[TableCatalog]:
    return db.query(TableCatalog).order_by(TableCatalog.schema_name, TableCatalog.table_name).all()


@router.post("/table-catalog", response_model=TableCatalogOut)
def upsert_table_catalog(payload: TableCatalogUpsert, db: Session = Depends(get_db)) -> TableCatalog:
    _connection(db, payload.connection_id)
    if error := table_catalog_error(payload.schema_name, payload.table_name, payload.columns_json):
        raise HTTPException(400, error)
    row = _catalog_row(db, payload.connection_id, payload.schema_name, payload.table_name)
    if not row:
        row = TableCatalog(
            connection_id=payload.connection_id,
            schema_name=payload.schema_name,
            table_name=payload.table_name,
        )
        db.add(row)
    row.description = payload.description
    row.columns_json = payload.columns_json
    row.agent_profile_json = payload.agent_profile_json
    row.can_create_rows = payload.can_create_rows
    row.updated_at = datetime.utcnow()
    db.flush()
    record_audit_event(
        db,
        "table_catalog.upserted",
        "table_catalog",
        row.id,
        payload={"connection_id": row.connection_id, "schema": row.schema_name, "table": row.table_name},
    )
    db.commit()
    db.refresh(row)
    return row


def _upsert_catalog(
    db: Session,
    connection_id: str,
    schema: str,
    table: str,
    inspector: Any,
) -> TableCatalog:
    row = _catalog_row(db, connection_id, schema, table)
    if not row:
        row = TableCatalog(connection_id=connection_id, schema_name=schema, table_name=table)
        db.add(row)
    row.columns_json = [
        {
            "name": column["name"],
            "type": str(column["type"]),
            "nullable": bool(column.get("nullable")),
            "default": str(column.get("default") or ""),
        }
        for column in inspector.get_columns(table, schema=schema)
    ]
    row.agent_profile_json = row.agent_profile_json or _default_agent_profile()
    row.last_introspected_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def _default_agent_profile() -> dict[str, Any]:
    return {
        "role": "candidate_destination",
        "requires_source_references": True,
        "search": {"semantic": True, "keyword": True, "bm25": True},
    }


def _is_user_schema(schema: str) -> bool:
    return not schema.startswith("pg_") and schema not in SYSTEM_SCHEMAS


def _new_engine_or_400(url: str):
    try:
        return checked_engine(url)
    except Exception as exc:
        raise HTTPException(400, {"code": "connection_failed", "message": connection_failure_message(exc, url)}) from exc


def _connection_engine_or_400(db: Session, connection: DatabaseConnection, action: str):
    url = _connection_url_or_400(connection)
    try:
        return url, checked_engine(url)
    except Exception as exc:
        message = connection_failure_message(exc, url)
        _record_connection_failure(db, connection, url, action, message)
        raise HTTPException(400, {"code": "connection_failed", "message": message}) from exc


def _record_connection_failure(db: Session, connection: DatabaseConnection, url: str, action: str, message: str) -> None:
    connection.capabilities_json = mark_connection_status(
        {**(connection.capabilities_json or {}), "secret_storage": secret_key_status()},
        url,
        "failed",
        message,
    )
    connection.updated_at = datetime.utcnow()
    record_audit_event(
        db,
        action,
        "database_connection",
        connection.id,
        payload={"status": "failed", "message": message},
    )
    db.commit()


def _catalog_row(db: Session, connection_id: str, schema: str, table: str) -> TableCatalog | None:
    return (
        db.query(TableCatalog)
        .filter(TableCatalog.connection_id == connection_id)
        .filter(TableCatalog.schema_name == schema)
        .filter(TableCatalog.table_name == table)
        .first()
    )


def _connection(db: Session, connection_id: str) -> DatabaseConnection:
    connection = db.get(DatabaseConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Database connection not found")
    return connection


def _connection_url_or_400(connection: DatabaseConnection) -> str:
    try:
        return connection_url(connection)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
