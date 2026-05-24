from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .connection_urls import connection_url
from .db import get_db
from .db_identifiers import first_identifier_error
from .load_modes import is_analysis_only
from .models import DatabaseConnection, Document, DocumentBlock, LoadPlan
from .row_identity import stable_row_id
from .row_review import row_is_loadable

router = APIRouter()


@router.get("/load-plans/{plan_id}/rows")
def loaded_rows(
    plan_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    if plan.status != "loaded":
        raise HTTPException(400, "Load plan is not loaded yet")
    if is_analysis_only(plan.target_mode, plan.target_table):
        raise HTTPException(400, "Analysis-only plans do not write target table rows")
    error = first_identifier_error(plan.schema_name, plan.target_table, plan.schema_json or {})
    if error:
        raise HTTPException(400, error)
    connection = _connection(db, plan)
    rows, total = _read_target_rows(connection, plan, limit, offset)
    return {
        "plan_id": plan.id,
        "status": plan.status,
        "destination": {
            "connection_id": connection.id,
            "schema_name": plan.schema_name,
            "target_table": plan.target_table,
        },
        "limit": limit,
        "offset": offset,
        "total": total,
        "rows": [_enrich_row(db, plan.dataset_id, row) for row in rows],
    }


@router.get("/load-plans/{plan_id}/preview-rows/{row_id}/source")
def preview_row_source(plan_id: str, row_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(LoadPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Load plan not found")
    row = _preview_row(plan, row_id)
    document_id = str(row.get("source_document_id") or "")
    block_id = str(row.get("source_block_id") or "")
    document = _document(db, plan.dataset_id, document_id)
    block = _block(db, document_id, block_id)
    return {
        "plan_id": plan.id,
        "row_id": stable_row_id(row),
        "row": _preview_source_row(row),
        "document": _document_payload(document, row),
        "block": _block_payload(block),
        "context": [_block_payload(item) for item in _context_blocks(db, document_id, block_id)],
        "warnings": _source_warnings(row, document, block),
    }


def _connection(db: Session, plan: LoadPlan) -> DatabaseConnection:
    connection = db.get(DatabaseConnection, plan.connection_id) if plan.connection_id else None
    connection = connection or db.query(DatabaseConnection).filter(DatabaseConnection.is_internal.is_(True)).first()
    if not connection:
        raise HTTPException(400, "Database connection is not configured")
    return connection


def _preview_row(plan: LoadPlan, row_id: str) -> dict[str, Any]:
    for row in plan.preview_rows or []:
        if stable_row_id(row) == row_id or str(row.get("row_id") or "") == row_id:
            return row
    raise HTTPException(404, "Preview row not found")


def _document(db: Session, dataset_id: str, document_id: str) -> Document | None:
    if not document_id:
        return None
    return db.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()


def _block(db: Session, document_id: str, block_id: str) -> DocumentBlock | None:
    if not document_id or not block_id:
        return None
    block = db.get(DocumentBlock, block_id)
    return block if block and block.document_id == document_id else None


def _context_blocks(db: Session, document_id: str, block_id: str) -> list[DocumentBlock]:
    if not document_id:
        return []
    blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).all()
    blocks = sorted(blocks, key=lambda item: (item.page or 0, item.sheet_name or "", item.slide_number or 0, item.id))
    index = next((idx for idx, item in enumerate(blocks) if item.id == block_id), 0)
    return blocks[max(0, index - 2): index + 3]


def _preview_source_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": stable_row_id(row),
        "source_document_id": row.get("source_document_id"),
        "source_block_id": row.get("source_block_id"),
        "source_file": row.get("source_file"),
        "page": row.get("page"),
        "sheet": row.get("sheet"),
        "confidence": row.get("confidence"),
        "row_status": row.get("row_status"),
        "validation_errors": row.get("validation_errors") or [],
        "field_values": row.get("field_values") or {},
        "field_sources": row.get("field_sources") or {},
        "content": row.get("content") or row.get("field_text") or "",
    }


def _document_payload(document: Document | None, row: dict[str, Any]) -> dict[str, Any]:
    if not document:
        return {"id": row.get("source_document_id"), "file_name": row.get("source_file"), "missing": True}
    return {
        "id": document.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "status": document.status,
        "sha256": document.sha256,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


def _block_payload(block: DocumentBlock | None) -> dict[str, Any]:
    if not block:
        return {}
    return {
        "id": block.id,
        "block_type": block.block_type,
        "page": block.page,
        "sheet_name": block.sheet_name,
        "slide_number": block.slide_number,
        "text": (block.text or "")[:1200],
        "table_json": block.table_json,
        "bbox": block.bbox,
        "confidence": block.confidence,
    }


def _source_warnings(row: dict[str, Any], document: Document | None, block: DocumentBlock | None) -> list[str]:
    warnings = []
    if not row.get("source_document_id"):
        warnings.append("missing_source_document_id")
    elif not document:
        warnings.append("source_document_not_found")
    if not row.get("source_block_id"):
        warnings.append("missing_source_block_id")
    elif not block:
        warnings.append("source_block_not_found")
    return warnings


def _read_target_rows(
    connection: DatabaseConnection,
    plan: LoadPlan,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    row_ids = _plan_row_ids(plan)
    if not row_ids:
        return [], 0
    engine = create_engine(connection_url(connection), pool_pre_ping=True, future=True)
    schema = _qi(plan.schema_name)
    table = _qi(plan.target_table)
    with engine.begin() as conn:
        total = int(
            conn.execute(
                text(f"SELECT count(*) FROM {schema}.{table} WHERE id = ANY(:ids)"),
                {"ids": row_ids},
            ).scalar() or 0
        )
        result = conn.execute(
            text(
                f"SELECT * FROM {schema}.{table} "
                "WHERE id = ANY(:ids) ORDER BY created_at DESC, id LIMIT :limit OFFSET :offset"
            ),
            {"ids": row_ids, "limit": limit, "offset": offset},
        )
        rows = [dict(row) for row in result.mappings()]
    return rows, total


def _plan_row_ids(plan: LoadPlan) -> list[str]:
    return [stable_row_id(row) for row in plan.preview_rows or [] if row_is_loadable(row)]


def _enrich_row(db: Session, dataset_id: str, row: dict[str, Any]) -> dict[str, Any]:
    document_id = str(row.get("source_document_id") or "")
    block_id = str(row.get("source_block_id") or "")
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.dataset_id == dataset_id)
        .first()
        if document_id
        else None
    )
    block = db.get(DocumentBlock, block_id) if block_id else None
    return {
        "id": _json_value(row.get("id")),
        "content": _json_value(row.get("content")),
        "field_values": _json_object(row.get("field_values")),
        "field_sources": _json_object(row.get("field_sources")),
        "metadata": _json_object(row.get("metadata")),
        "typed_columns": _typed_columns(row),
        "source": {
            "document_id": document_id,
            "block_id": block_id,
            "file_name": document.file_name if document else row.get("source_file"),
            "page": _json_value(row.get("page")),
            "sheet": _json_value(row.get("sheet")),
            "confidence": _json_value(row.get("confidence")),
            "evidence": (block.text or "")[:700] if block else "",
        },
        "created_at": _json_value(row.get("created_at")),
    }


def _typed_columns(row: dict[str, Any]) -> dict[str, Any]:
    managed = {
        "id",
        "content",
        "source_document_id",
        "source_block_id",
        "source_file",
        "page",
        "sheet",
        "confidence",
        "field_values",
        "field_sources",
        "metadata",
        "created_at",
    }
    return {key: _json_value(value) for key, value in row.items() if key not in managed}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return {}


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
