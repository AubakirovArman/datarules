import json
from collections import Counter
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .ai_summaries import document_ai_summary
from .config import get_settings
from .db import get_db
from .document_quality import build_quality_profile
from .models import Document, DocumentAiSummary, DocumentBlock, Dataset, TableCatalog
from .page_semantics import page_summaries
from .schema_chat_context import fallback_chat_schema, schema_chat_language, schema_chat_prompt, schema_chat_usage
from .schema_chat_guard import sanitize_schema_proposal
from .schemas import DocumentSummaryOut, SchemaChatRequest, SchemaChatResponse

router = APIRouter()


@router.get("/datasets/{dataset_id}/document-summaries", response_model=list[DocumentSummaryOut])
def document_summaries(
    dataset_id: str,
    language: str | None = Query(default=None, pattern="^(ru|kk|en)$"),
    db: Session = Depends(get_db),
) -> list[DocumentSummaryOut]:
    _require_dataset(db, dataset_id)
    documents = db.query(Document).filter(Document.dataset_id == dataset_id).all()
    return [_summary_for_document(db, document, language) for document in documents]


@router.post("/datasets/{dataset_id}/schema-chat", response_model=SchemaChatResponse)
def schema_chat(
    dataset_id: str,
    payload: SchemaChatRequest,
    db: Session = Depends(get_db),
) -> SchemaChatResponse:
    dataset = _require_dataset(db, dataset_id)
    snippets = _snippets(db, dataset_id)
    summaries = _ai_summaries(db, dataset_id, payload.language)
    tables = _known_tables(db)
    language = schema_chat_language(payload.language, summaries)
    proposal = _ask_gemma_for_schema(
        dataset,
        payload.message,
        snippets,
        tables,
        summaries,
        language,
    )
    proposal = sanitize_schema_proposal(proposal)
    proposal["context_usage"] = schema_chat_usage(language, summaries, snippets, tables)
    record_audit_event(
        db,
        "schema_chat.proposed",
        "dataset",
        dataset_id,
        dataset_id,
        {"message": payload.message, "source": proposal.get("source"), "table_name": proposal.get("table_name")},
    )
    db.commit()
    return SchemaChatResponse(
        assistant_message=str(proposal.get("assistant_message", "Schema proposal is ready.")),
        proposal_json=proposal,
    )


def _summary_for_document(db: Session, document: Document, language: str | None = None) -> DocumentSummaryOut:
    blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).all()
    block_counts = Counter(block.block_type for block in blocks)
    text_chars = sum(len(block.text or "") for block in blocks)
    pages = sorted({block.page for block in blocks if block.page is not None})
    sheets = sorted({block.sheet_name for block in blocks if block.sheet_name})
    slides = sorted({block.slide_number for block in blocks if block.slide_number is not None})
    ai_summary = document_ai_summary(db, document, blocks, language)
    summary = str(ai_summary.get("summary") or _plain_summary(document.file_name, block_counts, text_chars, pages, sheets, slides, language))
    return DocumentSummaryOut(
        document_id=document.id,
        file_name=document.file_name,
        file_type=document.file_type,
        status=document.status,
        summary=summary,
        blocks=len(blocks),
        pages=len(pages),
        sheets=sheets,
        slides=len(slides),
        tables=block_counts["table"],
        image_pages=block_counts["image_page"],
        text_chars=text_chars,
        page_summaries=page_summaries(blocks, ai_summary),
        quality_profile=build_quality_profile(blocks),
        summary_source=str(ai_summary.get("source", "deterministic")),
        ai_summary=ai_summary,
    )

def _plain_summary(
    file_name: str,
    counts: Counter,
    text_chars: int,
    pages: list[int],
    sheets: list[str],
    slides: list[int],
    language: str | None = None,
) -> str:
    if language == "kk":
        return f"{file_name}: {sum(counts.values())} блок, {text_chars} мәтін таңбасы алынды."
    if language == "ru":
        return f"{file_name}: извлечено блоков: {sum(counts.values())}, текстовых символов: {text_chars}."
    parts = [f"{file_name}: {sum(counts.values())} extracted blocks, {text_chars} text chars"]
    if pages:
        parts.append(f"{len(pages)} pages")
    if sheets:
        parts.append(f"{len(sheets)} sheets")
    if slides:
        parts.append(f"{len(slides)} slides")
    if counts["table"]:
        parts.append(f"{counts['table']} tables")
    if counts["image_page"]:
        parts.append(f"{counts['image_page']} image pages need OCR/multimodal review")
    return "; ".join(parts) + "."


def _snippets(db: Session, dataset_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(DocumentBlock, Document)
        .join(Document, Document.id == DocumentBlock.document_id)
        .filter(Document.dataset_id == dataset_id)
        .limit(80)
        .all()
    )
    return [
        {
            "file_name": document.file_name,
            "block_type": block.block_type,
            "page": block.page,
            "sheet": block.sheet_name,
            "text": (block.text or "")[:900],
        }
        for block, document in rows
    ]


def _known_tables(db: Session) -> list[dict[str, Any]]:
    rows = db.query(TableCatalog).order_by(TableCatalog.updated_at.desc()).limit(40).all()
    return [
        {
            "connection_id": row.connection_id,
            "schema": row.schema_name,
            "table": row.table_name,
            "description": row.description,
            "columns": row.columns_json,
            "agent_profile": row.agent_profile_json,
        }
        for row in rows
    ]


def _ai_summaries(db: Session, dataset_id: str, language: str | None) -> list[dict[str, Any]]:
    rows = (
        db.query(DocumentAiSummary, Document)
        .join(Document, Document.id == DocumentAiSummary.document_id)
        .filter(Document.dataset_id == dataset_id)
        .order_by(DocumentAiSummary.updated_at.desc())
        .all()
    )
    return [
        {
            "document_id": document.id,
            "file_name": document.file_name,
            "summary": _summary_variant(summary.summary_json, language),
        }
        for summary, document in rows
    ]


def _summary_variant(summary: dict[str, Any], language: str | None) -> dict[str, Any]:
    variants = summary.get("_language_variants") if isinstance(summary.get("_language_variants"), dict) else {}
    if language in {"ru", "kk", "en"} and isinstance(variants.get(language), dict):
        return variants[language]
    return {key: value for key, value in summary.items() if key != "_language_variants"}


def _ask_gemma_for_schema(
    dataset: Dataset,
    message: str,
    snippets: list[dict[str, Any]],
    known_tables: list[dict[str, Any]],
    ai_summaries: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.enable_gemma_calls or not settings.gemma_base_url:
        return fallback_chat_schema(dataset, message, language)
    body = {
        "model": settings.gemma_model_id,
        "temperature": 0.1,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": schema_chat_prompt(language)},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "dataset": dataset.name,
                        "request": message,
                        "expected_language": language,
                        "document_summaries": ai_summaries,
                        "snippets": snippets,
                        "known_tables": known_tables,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    try:
        url = settings.gemma_base_url.rstrip("/") + "/chat/completions"
        response = httpx.post(url, json=body, timeout=settings.gemma_timeout_seconds)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_json(content) | {"source": "gemma"}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        fallback = fallback_chat_schema(dataset, message, language)
        fallback["llm_error"] = str(exc)
        return fallback


def _parse_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise

def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset
