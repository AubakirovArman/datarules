import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .llm import GemmaClient
from .llm.gemma import SUMMARY_PROMPT_VERSION
from .models import Document, DocumentAiSummary, DocumentBlock, new_id

SUPPORTED_SUMMARY_LANGUAGES = {"ru", "kk", "en"}
ENGLISH_MARKERS = {"the", "document", "project", "investment", "contains", "summary", "reported", "total"}


def document_ai_summary(
    db: Session,
    document: Document,
    blocks: list[DocumentBlock],
    language: str | None = None,
) -> dict[str, Any]:
    fingerprint = _source_fingerprint(document, blocks)
    source_language = _language_hint(blocks)
    requested_language = _requested_language(language, source_language)
    row = _summary_row(db, document.id)
    cached = _cached_summary(row, fingerprint, requested_language)
    if cached:
        return cached
    summary = GemmaClient().summarize_document_sync(_document_payload(document, blocks, requested_language, source_language), _snippet_payload(blocks))
    summary["source_fingerprint"] = fingerprint
    summary["requested_language"] = requested_language
    summary["source_language"] = source_language
    _store_summary_row(db, document.id, row, requested_language, summary)
    db.commit()
    return summary


def _cached_summary(
    row: DocumentAiSummary | None,
    fingerprint: str,
    requested_language: str,
) -> dict[str, Any] | None:
    if not row:
        return None
    summary = row.summary_json or {}
    variants = summary.get("_language_variants") if isinstance(summary.get("_language_variants"), dict) else {}
    candidate = variants.get(requested_language)
    if isinstance(candidate, dict) and _matches(candidate, fingerprint, requested_language):
        return candidate
    if _matches(summary, fingerprint, requested_language):
        return _public_summary(summary)
    return None


def _summary_row(db: Session, document_id: str) -> DocumentAiSummary | None:
    return (
        db.query(DocumentAiSummary)
        .filter(DocumentAiSummary.document_id == document_id)
        .order_by(DocumentAiSummary.updated_at.desc())
        .first()
    )


def _store_summary_row(
    db: Session,
    document_id: str,
    row: DocumentAiSummary | None,
    language: str,
    summary: dict[str, Any],
) -> None:
    now = datetime.utcnow()
    summary_json = _store_language_variant(row.summary_json if row else {}, language, summary)
    source_model = str(summary.get("source", ""))
    if _dialect_name(db) == "postgresql":
        statement = insert(DocumentAiSummary).values(
            id=new_id("sum"),
            document_id=document_id,
            source_model=source_model,
            summary_json=summary_json,
            created_at=now,
            updated_at=now,
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=[DocumentAiSummary.document_id],
                set_={"source_model": source_model, "summary_json": summary_json, "updated_at": now},
            )
        )
        return
    row = row or DocumentAiSummary(document_id=document_id)
    row.source_model = source_model
    row.summary_json = summary_json
    row.updated_at = now
    db.add(row)


def _dialect_name(db: Session) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


def _store_language_variant(current: dict[str, Any], language: str, summary: dict[str, Any]) -> dict[str, Any]:
    variants = current.get("_language_variants") if isinstance(current.get("_language_variants"), dict) else {}
    clean = _public_summary(summary)
    return {**clean, "_language_variants": {**variants, language: clean}}


def _matches(summary: dict[str, Any], fingerprint: str, requested_language: str) -> bool:
    language = str(summary.get("requested_language") or summary.get("language") or "")
    return (
        summary.get("prompt_version") == SUMMARY_PROMPT_VERSION
        and summary.get("source_fingerprint") == fingerprint
        and language == requested_language
        and _language_ok(summary, requested_language)
    )


def _public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key != "_language_variants"}


def _source_fingerprint(document: Document, blocks: list[DocumentBlock]) -> str:
    payload = {
        "sha256": document.sha256,
        "file_type": document.file_type,
        "blocks": [
            {
                "page": block.page,
                "sheet": block.sheet_name,
                "slide": block.slide_number,
                "type": block.block_type,
                "text": block.text,
                "table": block.table_json,
                "confidence": round(float(block.confidence or 0), 4),
            }
            for block in blocks
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _document_payload(
    document: Document,
    blocks: list[DocumentBlock],
    requested_language: str,
    source_language: str,
) -> dict[str, Any]:
    pages = sorted({block.page for block in blocks if block.page is not None})
    sheets = sorted({block.sheet_name for block in blocks if block.sheet_name})
    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "status": document.status,
        "blocks": len(blocks),
        "pages": len(pages),
        "sheets": sheets,
        "language_hint": requested_language,
        "source_language_hint": source_language,
    }


def _snippet_payload(blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    return [
        {
            "block_id": block.id,
            "block_type": block.block_type,
            "page": block.page,
            "sheet": block.sheet_name,
            "text": (block.text or "")[:1200],
            "confidence": block.confidence,
        }
        for block in blocks[:100]
        if block.text
    ]


def _language_hint(blocks: list[DocumentBlock]) -> str:
    text = "\n".join((block.text or "")[:400] for block in blocks[:40])
    cyrillic = sum(1 for char in text if "А" <= char <= "я" or char in "ӘәҒғҚқҢңӨөҰұҮүҺһІі")
    kazakh = sum(1 for char in text if char in "ӘәҒғҚқҢңӨөҰұҮүҺһІі")
    latin = sum(1 for char in text if "A" <= char <= "z")
    if kazakh > 20:
        return "kk"
    if cyrillic >= latin:
        return "ru"
    return "en"


def _requested_language(language: str | None, fallback: str) -> str:
    return language if language in SUPPORTED_SUMMARY_LANGUAGES else fallback


def _language_ok(summary: dict[str, Any], requested_language: str) -> bool:
    if requested_language not in {"ru", "kk"}:
        return True
    text = " " + _human_text(summary).lower() + " "
    cyrillic = sum(1 for char in text if "а" <= char <= "я" or char in "әғқңөұүһі")
    latin = sum(1 for char in text if "a" <= char <= "z")
    markers = sum(1 for marker in ENGLISH_MARKERS if f" {marker} " in text)
    return not (markers >= 2 and latin > cyrillic)


def _human_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_human_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_human_text(item) for item in value)
    return str(value)
