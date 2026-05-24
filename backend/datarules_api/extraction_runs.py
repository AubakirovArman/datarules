import json
from pathlib import Path
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from .config import get_settings
from .document_quality import build_quality_profile
from .models import Document, DocumentBlock, DocumentExtractionRun
from .parsers.common import clean_json, clean_text

PARSER_VERSION = "datarules_parser_v1"


def record_extraction_run(
    db: Session,
    document: Document,
    blocks: list[DocumentBlock],
    canonical: dict[str, Any],
    run_type: str,
    status: str | None = None,
    error_message: str = "",
) -> DocumentExtractionRun:
    run = DocumentExtractionRun(
        dataset_id=document.dataset_id,
        document_id=document.id,
        run_type=clean_text(run_type),
        status=clean_text(status or document.status or "completed"),
        parser_version=PARSER_VERSION,
        quality_json=build_quality_profile(blocks),
        metrics_json=_metrics(blocks),
        error_message=clean_text(error_message),
    )
    db.add(run)
    db.flush()
    path = snapshot_path(document.id, run.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _snapshot_payload(canonical, run)
    path.write_text(json.dumps(jsonable_encoder(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    run.canonical_path = str(path)
    db.flush()
    return run


def list_extraction_runs(db: Session, dataset_id: str, document_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(DocumentExtractionRun)
        .filter(DocumentExtractionRun.dataset_id == dataset_id)
        .filter(DocumentExtractionRun.document_id == document_id)
        .order_by(DocumentExtractionRun.created_at.desc())
        .all()
    )
    return [run_to_dict(row) for row in rows]


def backfill_missing_extraction_runs() -> int:
    from .db import SessionLocal

    count = 0
    with SessionLocal() as db:
        documents = db.query(Document).all()
        for document in documents:
            exists = db.query(DocumentExtractionRun.id).filter(DocumentExtractionRun.document_id == document.id).first()
            if exists:
                continue
            blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).all()
            if not blocks:
                continue
            canonical = _load_current_canonical(document.id) or _canonical_from_blocks(document, blocks)
            record_extraction_run(db, document, blocks, canonical, "legacy_import", document.status)
            count += 1
        if count:
            db.commit()
    return count


def run_to_dict(run: DocumentExtractionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "document_id": run.document_id,
        "run_type": run.run_type,
        "status": run.status,
        "parser_version": run.parser_version,
        "quality": run.quality_json or {},
        "metrics": run.metrics_json or {},
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def load_run_snapshot(run: DocumentExtractionRun) -> dict[str, Any]:
    path = Path(run.canonical_path)
    if not path.exists():
        raise FileNotFoundError(run.canonical_path)
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_path(document_id: str, run_id: str) -> Path:
    return get_settings().canonical_storage_dir / "runs" / document_id / f"{run_id}.json"


def current_canonical_path(document_id: str) -> Path:
    return get_settings().canonical_storage_dir / f"{document_id}.json"


def snapshot_blocks(document_id: str, snapshot: dict[str, Any]) -> list[DocumentBlock]:
    blocks = []
    for item in snapshot.get("blocks") or []:
        if isinstance(item, dict):
            blocks.append(_block_from_snapshot(document_id, item))
    return blocks


def write_current_canonical(document_id: str, canonical: dict[str, Any]) -> None:
    path = current_canonical_path(document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable_encoder(canonical), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_current_canonical(document_id: str) -> dict[str, Any] | None:
    path = current_canonical_path(document_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _canonical_from_blocks(document: Document, blocks: list[DocumentBlock]) -> dict[str, Any]:
    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "document_status": document.status,
        "parser_version": PARSER_VERSION,
        "run_type": "legacy_import",
        "sha256": document.sha256,
        "metadata": {"source": "backfill"},
        "blocks": [_block_to_json(block) for block in blocks],
    }


def _block_from_snapshot(document_id: str, item: dict[str, Any]) -> DocumentBlock:
    block_id = clean_text(str(item.get("block_id") or ""))
    values = {
        "document_id": document_id,
        "page": item.get("page"),
        "sheet_name": clean_text(str(item.get("sheet_name") or "")) or None,
        "slide_number": item.get("slide_number"),
        "block_type": clean_text(str(item.get("type") or item.get("block_type") or "paragraph")),
        "text": clean_text(str(item.get("text") or "")),
        "table_json": clean_json(item.get("table_json")),
        "bbox": clean_json(item.get("bbox")),
        "confidence": float(item.get("confidence") or 0.0),
    }
    if block_id:
        values["id"] = block_id
    return DocumentBlock(**values)


def _block_to_json(block: DocumentBlock) -> dict[str, Any]:
    return {
        "block_id": block.id,
        "type": block.block_type,
        "page": block.page,
        "sheet_name": block.sheet_name,
        "slide_number": block.slide_number,
        "text": block.text,
        "table_json": block.table_json,
        "bbox": block.bbox,
        "confidence": block.confidence,
    }


def _snapshot_payload(canonical: dict[str, Any], run: DocumentExtractionRun) -> dict[str, Any]:
    payload = dict(clean_json(canonical) or {})
    payload["extraction_run"] = {
        "id": run.id,
        "run_type": run.run_type,
        "status": run.status,
        "parser_version": run.parser_version,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    return payload


def _metrics(blocks: list[DocumentBlock]) -> dict[str, Any]:
    pages = {block.page for block in blocks if block.page is not None}
    sheets = {block.sheet_name for block in blocks if block.sheet_name}
    slides = {block.slide_number for block in blocks if block.slide_number is not None}
    return {
        "blocks": len(blocks),
        "pages": len(pages),
        "sheets": len(sheets),
        "slides": len(slides),
        "tables": sum(1 for block in blocks if block.block_type == "table"),
        "text_chars": sum(len(block.text or "") for block in blocks),
        "low_confidence": sum(1 for block in blocks if block.confidence < 0.75),
    }
