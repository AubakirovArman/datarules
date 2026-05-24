import re
from typing import Any

from sqlalchemy.orm import Session

from .db_identifiers import MANAGED_COLUMNS
from .field_provenance import build_field_sources
from .llm.records import extract_records_sync
from .models import DatabaseConnection, Document, DocumentAiSummary, DocumentBlock, DocumentReview, TableCatalog
from .normalization_schemas import DEFAULT_COLUMNS
from .parsers.common import clean_json, clean_text

SOURCE_COLUMNS = MANAGED_COLUMNS

def prepare_load_preview(
    db: Session,
    dataset_id: str,
    connection: DatabaseConnection | None,
    schema_name: str,
    target_mode: str,
    target_table: str,
    supplied_schema: dict[str, Any],
    document_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    schema_json = dict(supplied_schema or target_schema(db, connection, schema_name, target_table))
    scoped_ids = [item for item in document_ids or [] if item]
    if scoped_ids:
        schema_json["document_scope"] = {"document_ids": scoped_ids}
    documents = _scoped_documents(db, dataset_id, target_table, target_mode, scoped_ids)
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for document in documents[:20]:
        blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).all()
        summary = _ai_summary(db, document.id)
        snippets = _snippets(blocks)
        extracted = extract_records_sync(_document_payload(document, summary), schema_json, snippets)
        issues.extend(_document_issues(document, extracted.get("quality_issues", [])))
        gemma_rows = _rows_from_extraction(document, blocks, schema_json, extracted)
        rows.extend(gemma_rows or [_fallback_row(document, blocks, schema_json, summary)])
    return rows[:100], schema_json, issues


def target_schema(
    db: Session,
    connection: DatabaseConnection | None,
    schema_name: str,
    target_table: str,
) -> dict[str, Any]:
    catalog = _catalog(db, connection.id if connection else None, schema_name, target_table)
    existing = catalog.columns_json if catalog else []
    columns = _target_columns(existing, target_table)
    return {
        "connection_id": connection.id if connection else None,
        "schema_name": schema_name,
        "table_name": target_table,
        "description": catalog.description if catalog else _default_description(target_table),
        "existing_columns": existing,
        "target_columns": columns,
        "source_references_required": True,
        "agent_columns": ["source_document_id", "source_block_id", "confidence", "embedding", "search_tsv"],
    }


def _rows_from_extraction(
    document: Document,
    blocks: list[DocumentBlock],
    schema_json: dict[str, Any],
    extracted: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    records = extracted.get("records") if isinstance(extracted, dict) else []
    block_map = {block.id: block for block in blocks}
    for index, record in enumerate(records or [], start=1):
        if not isinstance(record, dict):
            continue
        fields = _allowed_fields(record.get("field_values"), schema_json)
        source_block_id = str(record.get("source_block_id") or _first_block_id(blocks))
        source_block = block_map.get(source_block_id)
        content = clean_text(str(record.get("content") or _content_from_fields(fields) or document.file_name))
        confidence = _confidence(record.get("confidence"), blocks)
        field_sources = build_field_sources(
            document,
            fields,
            source_block,
            record.get("field_sources") or record.get("source_references"),
            confidence,
            extracted.get("source"),
        )
        rows.append(_row(document, index, fields, field_sources, source_block, source_block_id, content, confidence, extracted.get("source")))
    return rows


def _fallback_row(
    document: Document,
    blocks: list[DocumentBlock],
    schema_json: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    text = "\n".join(block.text or "" for block in blocks[:30])
    amount, currency = _extract_amount(text)
    fields = {}
    for column in schema_json.get("target_columns", []):
        name = column.get("name")
        if not name:
            continue
        fields[name] = _fallback_value(str(name), document, text, summary, amount, currency)
    content = clean_text(str(summary.get("summary") or text[:900] or document.file_name))
    confidence = min(0.78, max((block.confidence for block in blocks), default=0.55))
    source_block = blocks[0] if blocks else None
    field_sources = build_field_sources(document, fields, source_block, None, confidence, "deterministic_fallback")
    return _row(document, 1, fields, field_sources, source_block, _first_block_id(blocks), content, confidence, "deterministic_fallback")


def _row(
    document: Document,
    index: int,
    fields: dict[str, Any],
    field_sources: dict[str, Any],
    source_block: DocumentBlock | None,
    source_block_id: str,
    content: str,
    confidence: float,
    source: str | None,
) -> dict[str, Any]:
    errors = _validation_errors(fields, source_block_id)
    return {
        "row_id": f"{document.id}:{index}",
        "source_document_id": document.id,
        "source_file": document.file_name,
        "source_block_id": source_block_id,
        "page": source_block.page if source_block else None,
        "sheet": source_block.sheet_name if source_block else None,
        "content": content[:1600],
        "field_text": content[:800],
        "field_values": clean_json(fields),
        "field_sources": clean_json(field_sources),
        "confidence": confidence,
        "extraction_source": source or "unknown",
        "validation_errors": errors,
    }


def _target_columns(existing: list[dict[str, Any]], target_table: str) -> list[dict[str, Any]]:
    columns = []
    for column in existing:
        name = str(column.get("name", ""))
        if name and name not in SOURCE_COLUMNS:
            columns.append({"name": name, "type": str(column.get("type", "text")), "required": False})
    if columns:
        return columns[:30]
    default = DEFAULT_COLUMNS.get(target_table, [("title", "text", True), ("summary", "text", False)])
    return [{"name": name, "type": kind, "required": required} for name, kind, required in default]


def _allowed_fields(value: Any, schema_json: dict[str, Any]) -> dict[str, Any]:
    allowed = {str(column.get("name")) for column in schema_json.get("target_columns", [])}
    if not isinstance(value, dict):
        return {}
    return {key: clean_json(item) for key, item in value.items() if key in allowed}


def _validation_errors(fields: dict[str, Any], source_block_id: str) -> list[str]:
    errors = []
    if not source_block_id:
        errors.append("missing_source_block_id")
    if not any(value not in (None, "") for value in fields.values()):
        errors.append("empty_field_values")
    return errors


def _fallback_value(
    name: str,
    document: Document,
    text: str,
    summary: dict[str, Any],
    amount: str | None,
    currency: str | None,
) -> Any:
    if name in {"project_name", "milestone_name", "title"}:
        return _first_entity(summary, "project") or document.file_name
    if name in {"company_name", "company"}:
        return _first_entity(summary, "company")
    if name in {"description", "summary", "content"}:
        return summary.get("summary") or text[:500]
    if name == "amount":
        return amount
    if name == "currency":
        return currency
    if name == "year":
        match = re.search(r"\b(20\d{2})\b", text)
        return match.group(1) if match else None
    if name == "metric_name":
        return "document_value"
    return None


def _extract_amount(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"(\d[\d\s,.]*)\s*(трлн|млрд|млн|тыс)?\s*(тенге|тг|kzt|usd|\$|eur)?", text, re.I)
    if not match:
        return None, None
    amount = " ".join(part for part in match.groups()[:2] if part)
    currency = match.group(3)
    if currency == "$":
        currency = "USD"
    return amount.strip(), currency.upper() if currency else None


def _first_entity(summary: dict[str, Any], kind: str) -> str | None:
    for entity in summary.get("entities", []):
        if isinstance(entity, dict) and str(entity.get("type", "")).lower() == kind:
            return str(entity.get("name"))
    return None


def _scoped_documents(
    db: Session,
    dataset_id: str,
    target_table: str,
    target_mode: str,
    document_ids: list[str],
) -> list[Document]:
    confirmed = [
        row[0]
        for row in db.query(DocumentReview.document_id)
        .filter(DocumentReview.dataset_id == dataset_id, DocumentReview.status == "confirmed")
        .filter(DocumentReview.selected_table == target_table)
        .all()
    ]
    query = db.query(Document).filter(Document.dataset_id == dataset_id)
    if document_ids:
        query = query.filter(Document.id.in_(document_ids))
    elif confirmed:
        query = query.filter(Document.id.in_(confirmed))
    elif target_mode == "existing":
        query = query.order_by(Document.created_at.desc())
    return query.all()


def _snippets(blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    return [
        {
            "block_id": block.id,
            "block_type": block.block_type,
            "page": block.page,
            "sheet": block.sheet_name,
            "text": (block.text or "")[:1400],
            "confidence": block.confidence,
        }
        for block in blocks[:120]
        if block.text
    ]


def _document_payload(document: Document, summary: dict[str, Any]) -> dict[str, Any]:
    return {"document_id": document.id, "file_name": document.file_name, "summary": summary}


def _document_issues(document: Document, issues: list[Any]) -> list[dict[str, Any]]:
    return [{"severity": "warning", "code": "extractor_note", "document": document.file_name, "message": str(item)} for item in issues]


def _ai_summary(db: Session, document_id: str) -> dict[str, Any]:
    row = db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document_id).order_by(DocumentAiSummary.updated_at.desc()).first()
    return row.summary_json if row else {}


def _catalog(db: Session, connection_id: str | None, schema: str, table: str) -> TableCatalog | None:
    if not connection_id:
        return None
    return db.query(TableCatalog).filter_by(connection_id=connection_id, schema_name=schema, table_name=table).first()


def _first_block_id(blocks: list[DocumentBlock]) -> str:
    return blocks[0].id if blocks else ""


def _content_from_fields(fields: dict[str, Any]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in fields.items() if value not in (None, ""))


def _confidence(value: Any, blocks: list[DocumentBlock]) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return min(0.85, max((block.confidence for block in blocks), default=0.65))


def _default_description(table: str) -> str:
    return f"DataRules structured table for {table.replace('_', ' ')}."
