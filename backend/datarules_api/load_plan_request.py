from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .db_identifiers import MANAGED_COLUMNS
from .models import SchemaVersion


class LoadPlanCreate(BaseModel):
    connection_id: str | None = None
    schema_name: str = "public"
    target_mode: str = "existing"
    target_table: str
    document_ids: list[str] = Field(default_factory=list)
    schema_version_id: str | None = None
    plan_schema: dict[str, Any] = Field(default_factory=dict, alias="schema_json")

    model_config = ConfigDict(populate_by_name=True)


def schema_for_load_plan(db: Session, dataset_id: str, payload: LoadPlanCreate) -> dict[str, Any]:
    if not payload.schema_version_id:
        user = _user_schema(payload.plan_schema)
        return user or _active_version_schema(db, dataset_id, payload.target_table.strip()) or {}
    row = db.get(SchemaVersion, payload.schema_version_id)
    if not row or row.dataset_id != dataset_id:
        raise HTTPException(404, "Schema version not found")
    schema = _version_schema(row, payload.target_table.strip())
    schema["schema_version"] = {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "proposal_id": row.proposal_id,
    }
    return schema


def _user_schema(schema: dict[str, Any]) -> dict[str, Any]:
    row = dict(schema or {})
    if isinstance(row.get("target_columns"), list) and row["target_columns"]:
        row.setdefault("schema_source", "user_supplied_schema")
    return row


def _active_version_schema(db: Session, dataset_id: str, target_table: str) -> dict[str, Any] | None:
    rows = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.dataset_id == dataset_id, SchemaVersion.status == "active")
        .order_by(SchemaVersion.version.desc())
        .all()
    )
    for row in rows:
        if _matching_table((row.schema_json or {}).get("tables"), target_table):
            schema = _version_schema(row, target_table)
            schema["schema_version"] = {"id": row.id, "version": row.version, "status": row.status, "proposal_id": row.proposal_id}
            return schema
    return None


def _version_schema(row: SchemaVersion, target_table: str) -> dict[str, Any]:
    raw = row.schema_json or {}
    if isinstance(raw.get("target_columns"), list):
        return dict(raw)
    table = _matching_table(raw.get("tables"), target_table)
    columns = _columns(table.get("columns") if table else [])
    return {
        "description": str((table or {}).get("purpose") or (table or {}).get("description") or row.summary),
        "table_name": target_table,
        "target_columns": columns or [{"name": "title", "type": "text", "required": False}],
        "source_references_required": True,
        "schema_version_source": "approved_schema_version",
    }


def _matching_table(value: Any, target_table: str) -> dict[str, Any] | None:
    tables = value if isinstance(value, list) else []
    candidates = [item for item in tables if isinstance(item, dict)]
    for table in candidates:
        if str(table.get("name") or table.get("table_name") or "") == target_table:
            return table
    return candidates[0] if candidates else None


def _columns(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in MANAGED_COLUMNS:
            continue
        rows.append({"name": name, "type": str(item.get("type") or "text"), "required": bool(item.get("required"))})
    return rows[:40]
