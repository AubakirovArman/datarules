from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import get_db
from .models import Dataset, SchemaProposal, SchemaVersion

router = APIRouter()


@router.get("/datasets/{dataset_id}/schema-versions")
def list_schema_versions(dataset_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found")
    rows = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.dataset_id == dataset_id)
        .order_by(SchemaVersion.version.desc(), SchemaVersion.created_at.desc())
        .all()
    )
    return [_version_payload(row) for row in rows]


def approve_schema_version(db: Session, proposal: SchemaProposal) -> SchemaVersion:
    existing = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.dataset_id == proposal.dataset_id, SchemaVersion.proposal_id == proposal.id)
        .first()
    )
    if existing:
        _activate_only(db, existing)
        return existing
    version = _next_version(db, proposal.dataset_id)
    row = SchemaVersion(
        dataset_id=proposal.dataset_id,
        proposal_id=proposal.id,
        version=version,
        status="active",
        schema_json=_schema_json(proposal.proposal_json or {}),
        summary=_summary(proposal.proposal_json or {}),
    )
    db.add(row)
    db.flush()
    _activate_only(db, row)
    return row


def _activate_only(db: Session, active: SchemaVersion) -> None:
    db.query(SchemaVersion).filter(
        SchemaVersion.dataset_id == active.dataset_id,
        SchemaVersion.id != active.id,
        SchemaVersion.status == "active",
    ).update({"status": "archived"})
    active.status = "active"


def _next_version(db: Session, dataset_id: str) -> int:
    latest = db.query(func.max(SchemaVersion.version)).filter(SchemaVersion.dataset_id == dataset_id).scalar()
    return int(latest or 0) + 1


def _schema_json(proposal: dict[str, Any]) -> dict[str, Any]:
    schema = proposal.get("schema_json")
    if isinstance(schema, dict) and schema:
        return schema
    tables = proposal.get("tables") if isinstance(proposal.get("tables"), list) else []
    return {
        "description": str(proposal.get("dataset_summary") or proposal.get("assistant_message") or ""),
        "tables": tables,
        "source_references_required": True,
    }


def _summary(proposal: dict[str, Any]) -> str:
    text = proposal.get("dataset_summary") or proposal.get("assistant_message") or proposal.get("description") or ""
    if text:
        return str(text)[:1200]
    tables = proposal.get("tables") if isinstance(proposal.get("tables"), list) else []
    names = [str(item.get("name") or item.get("table_name") or item) for item in tables[:6] if isinstance(item, dict)]
    return ", ".join(names)


def _version_payload(row: SchemaVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "proposal_id": row.proposal_id,
        "version": row.version,
        "status": row.status,
        "schema_json": row.schema_json,
        "summary": row.summary,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else None,
    }
