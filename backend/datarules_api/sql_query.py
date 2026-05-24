import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .connection_urls import connection_url
from .db import get_db
from .db_identifiers import first_identifier_error
from .models import DatabaseConnection, Dataset, LoadPlan

router = APIRouter()
BLOCKED = {
    "alter",
    "analyze",
    "call",
    "copy",
    "create",
    "delete",
    "drop",
    "grant",
    "insert",
    "merge",
    "refresh",
    "reindex",
    "revoke",
    "truncate",
    "update",
    "vacuum",
}


class SqlQueryRequest(BaseModel):
    sql: str
    plan_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


@router.post("/datasets/{dataset_id}/sql-query")
def dataset_sql_query(dataset_id: str, payload: SqlQueryRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found")
    plan = _plan(db, dataset_id, payload.plan_id)
    _validate_plan(plan)
    sql = _safe_sql(payload.sql, plan)
    connection = _connection(db, plan)
    rows = _execute(connection, plan.schema_name, sql, payload.limit)
    return {
        "dataset_id": dataset_id,
        "plan_id": plan.id,
        "schema_name": plan.schema_name,
        "target_table": plan.target_table,
        "limit": payload.limit,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": rows,
    }


def _plan(db: Session, dataset_id: str, plan_id: str | None) -> LoadPlan:
    query = db.query(LoadPlan).filter(LoadPlan.dataset_id == dataset_id, LoadPlan.status == "loaded")
    if plan_id:
        plan = db.query(LoadPlan).filter(LoadPlan.dataset_id == dataset_id, LoadPlan.id == plan_id).first()
        if not plan:
            raise HTTPException(404, "Load plan not found")
        if plan.status != "loaded":
            raise HTTPException(409, "Confirm the load plan before running SQL")
        return plan
    plans = query.order_by(LoadPlan.updated_at.desc(), LoadPlan.created_at.desc()).all()
    if not plans:
        raise HTTPException(409, "No loaded tables are available for SQL queries")
    if len(plans) > 1:
        raise HTTPException(400, "Choose a load plan before running SQL")
    return plans[0]


def _validate_plan(plan: LoadPlan) -> None:
    error = first_identifier_error(plan.schema_name, plan.target_table, plan.schema_json or {})
    if error:
        raise HTTPException(400, error)


def _safe_sql(raw: str, plan: LoadPlan) -> str:
    sql = raw.strip()
    lowered = re.sub(r"\s+", " ", sql.lower())
    if not lowered.startswith("select "):
        raise HTTPException(400, "Only SELECT queries are allowed")
    if any(token in sql for token in (";", "--", "/*", "*/")):
        raise HTTPException(400, "SQL comments and multiple statements are not allowed")
    blocked = [word for word in BLOCKED if re.search(rf"\b{word}\b", lowered)]
    if blocked:
        raise HTTPException(400, f"SQL contains blocked keyword: {blocked[0]}")
    if not _mentions_target(lowered, plan):
        raise HTTPException(400, "Query must reference the selected target table")
    return sql


def _mentions_target(lowered: str, plan: LoadPlan) -> bool:
    table = re.escape(plan.target_table.lower())
    schema = re.escape(plan.schema_name.lower())
    patterns = [
        rf"\bfrom\s+{table}\b",
        rf"\bjoin\s+{table}\b",
        rf"\bfrom\s+{schema}\.{table}\b",
        rf"\bjoin\s+{schema}\.{table}\b",
        rf'\bfrom\s+"{schema}"\."{table}"\b',
        rf'\bfrom\s+"{table}"\b',
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def _connection(db: Session, plan: LoadPlan) -> DatabaseConnection:
    connection = db.get(DatabaseConnection, plan.connection_id) if plan.connection_id else None
    connection = connection or db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()
    if not connection:
        raise HTTPException(400, "Database connection is not configured")
    return connection


def _execute(connection: DatabaseConnection, schema: str, sql: str, limit: int) -> list[dict[str, Any]]:
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    wrapped = f"SELECT * FROM ({sql}) AS datarules_sql_query LIMIT :limit"
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL statement_timeout = '15s'"))
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text(f"SET LOCAL search_path TO {_qi(schema)}"))
        result = conn.execute(text(wrapped), {"limit": limit}).mappings().all()
    return [{key: _json_value(value) for key, value in row.items()} for row in result]


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
