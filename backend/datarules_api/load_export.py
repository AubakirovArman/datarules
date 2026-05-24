import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .connection_urls import connection_url
from .db import get_db
from .load_modes import is_analysis_only
from .models import DatabaseConnection, LoadPlan
from .row_identity import stable_row_id

router = APIRouter()


@router.get("/load-plans/{plan_id}/export.json")
def export_load_plan_json(plan_id: str, db: Session = Depends(get_db)) -> Response:
    rows = _export_rows(db, plan_id)
    return Response(
        content=json.dumps({"plan_id": plan_id, "rows": rows}, ensure_ascii=False, default=_json_default),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'},
    )


@router.get("/load-plans/{plan_id}/export.csv")
def export_load_plan_csv(plan_id: str, db: Session = Depends(get_db)) -> Response:
    rows = _export_rows(db, plan_id)
    output = io.StringIO()
    columns = _csv_columns(rows)
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _csv_value(row.get(column)) for column in columns})
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{plan_id}.csv"'},
    )


def _export_rows(db: Session, plan_id: str) -> list[dict[str, Any]]:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    if plan.status != "loaded":
        raise HTTPException(400, "Only loaded plans can be exported")
    if is_analysis_only(plan.target_mode, plan.target_table):
        return [_preview_export_row(row) for row in plan.preview_rows or [] if row.get("source_block_id")]
    row_ids = [stable_row_id(row) for row in plan.preview_rows or [] if row.get("source_block_id")]
    if not row_ids:
        return []
    connection = _connection(db, plan)
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    with engine.begin() as conn:
        columns = _table_columns(conn, plan.schema_name, plan.target_table)
        selected = _selected_columns(columns)
        rows = conn.execute(
            text(
                f"SELECT {', '.join(_qi(column) for column in selected)} "
                f"FROM {_qi(plan.schema_name)}.{_qi(plan.target_table)} "
                "WHERE id = ANY(:ids) ORDER BY created_at, id"
            ),
            {"ids": row_ids},
        ).mappings()
        return [dict(row) for row in rows]


def _connection(db: Session, plan: LoadPlan) -> DatabaseConnection:
    connection = db.get(DatabaseConnection, plan.connection_id) if plan.connection_id else None
    connection = connection or db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()
    if not connection:
        raise HTTPException(400, "Database connection is not configured")
    return connection


def _table_columns(conn: Any, schema: str, table: str) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"schema": schema, "table": table},
    ).all()
    columns = [row[0] for row in rows]
    if "id" not in columns:
        raise HTTPException(400, "Target table is not exportable")
    return columns


def _selected_columns(columns: list[str]) -> list[str]:
    base = ["id", "content", "source_file", "page", "sheet", "confidence", "field_values", "field_sources", "created_at"]
    extras = [column for column in columns if column not in base and not column.startswith("source_")]
    return [column for column in [*base, *extras] if column in columns]


def _csv_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns or ["id"]


def _preview_export_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": stable_row_id(row),
        "content": row.get("content") or row.get("field_text") or "",
        "source_file": row.get("source_file"),
        "page": row.get("page"),
        "sheet": row.get("sheet"),
        "confidence": row.get("confidence"),
        "field_values": row.get("field_values") or {},
        "field_sources": row.get("field_sources") or {},
    }


def _csv_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=_json_default)
    if value is None:
        return ""
    return str(value)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
