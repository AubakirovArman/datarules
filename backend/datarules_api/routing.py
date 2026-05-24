from collections import Counter
import re

from sqlalchemy.orm import Session

from .models import Document, DocumentAiSummary, DocumentBlock, DocumentReview, TableCatalog


DOC_TYPE_OPTIONS = [
    ("management_conclusion", "Director conclusion / Заключение директора"),
    ("monitoring_report", "Monitoring report / Отчет мониторинга"),
    ("investment_project", "Investment project / Инвестиционный проект"),
    ("financial_report", "Financial report / Финансовый отчет"),
    ("company_profile", "Company profile / Профиль компании"),
    ("contract_or_agreement", "Contract or agreement / Договор"),
    ("presentation", "Presentation / Презентация"),
    ("raw_reference", "Reference document / Справочный документ"),
]

TABLE_OPTIONS = [
    ("investment_projects", "Project master data"),
    ("project_financials", "Amounts, CAPEX, OPEX, currency, year"),
    ("project_milestones", "Dates, stages, deadlines, status"),
    ("companies", "Companies, owners, counterparties"),
    ("documents_raw", "Keep as source-only document"),
    ("analysis_only", "Analyze without loading into a business table yet"),
]

DOC_SIGNALS = {
    "management_conclusion": ["заключение директора", "итоговое решение", "пункт повестки", "директор"],
    "monitoring_report": ["мониторинг", "портфель", "освоение", "исполнение", "крупных инвестиционных"],
    "investment_project": ["project", "проект", "жоба", "capex", "investment"],
    "financial_report": ["financial report", "финансовый отчет", "budget", "currency", "баланс", "выручка"],
    "company_profile": ["company", "компания", "ұйым", "bin", "address"],
    "contract_or_agreement": ["agreement", "contract", "договор", "келісім", "party", "контракт"],
    "presentation": ["slide", "presentation", "презентация"],
    "raw_reference": ["qr-код", "справка", "reference"],
}

TABLE_SIGNALS = {
    "investment_projects": ["project", "проект", "жоба", "status", "region", "портфель"],
    "project_financials": ["capex", "opex", "amount", "сумма", "usd", "kzt", "тенге", "млрд"],
    "project_milestones": ["date", "deadline", "start", "end", "milestone", "срок", "завершение"],
    "companies": ["company", "компания", "ұйым", "counterparty", "акционер"],
    "documents_raw": ["qr-код", "source-only", "raw"],
    "analysis_only": ["ambiguous", "unclear", "review"],
}


def create_document_review(
    db: Session,
    document: Document,
    blocks: list[DocumentBlock],
    ai_summary: dict | None = None,
) -> None:
    existing = db.query(DocumentReview).filter(DocumentReview.document_id == document.id).first()
    if existing and existing.status == "confirmed":
        return
    db.query(DocumentReview).filter(DocumentReview.document_id == document.id).delete()
    fragments = [block.text for block in blocks[:60] if block.text] + _summary_text(ai_summary)
    text = "\n".join(fragments).lower()
    block_types = Counter(block.block_type for block in blocks)

    doc_options = _rank_doc_types(document, text, fragments, block_types)
    table_options = _rank_tables(db, text, fragments, block_types, ai_summary)
    confidence = max(option["confidence"] for option in doc_options)
    status = "suggested" if confidence >= 0.78 else "needs_user_choice"

    review = DocumentReview(
        dataset_id=document.dataset_id,
        document_id=document.id,
        status=status,
        reason=_reason(confidence, doc_options, table_options, block_types),
        doc_type_options=doc_options,
        table_options=table_options,
        selected_doc_type=doc_options[0]["value"] if status == "suggested" else None,
        selected_table=table_options[0]["value"] if status == "suggested" else None,
    )
    db.add(review)


def refresh_document_reviews(db: Session, dataset_id: str) -> None:
    documents = db.query(Document).filter(Document.dataset_id == dataset_id).all()
    for document in documents:
        review = db.query(DocumentReview).filter(DocumentReview.document_id == document.id).first()
        if review and review.status == "confirmed":
            continue
        blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).all()
        summary = (
            db.query(DocumentAiSummary)
            .filter(DocumentAiSummary.document_id == document.id)
            .order_by(DocumentAiSummary.updated_at.desc())
            .first()
        )
        create_document_review(db, document, blocks, summary.summary_json if summary else None)
    db.commit()


def _rank_doc_types(document: Document, text: str, fragments: list[str], block_types: Counter) -> list[dict]:
    scores = {key: _hit_score(text, words) for key, words in DOC_SIGNALS.items()}
    if "заключение директора" in text:
        scores["management_conclusion"] += 12
    if "мониторинг" in text and "проект" in text:
        scores["monitoring_report"] += 8
    if document.file_name.lower().endswith((".ppt", ".pptx")) or block_types["slide"]:
        scores["presentation"] += 4
    scores["raw_reference"] += 1
    return _options(DOC_TYPE_OPTIONS, scores, DOC_SIGNALS, fragments, "document_classifier")


def _rank_tables(
    db: Session,
    text: str,
    fragments: list[str],
    block_types: Counter,
    ai_summary: dict | None,
) -> list[dict]:
    scores = {key: _hit_score(text, words) for key, words in TABLE_SIGNALS.items()}
    scores["documents_raw"] += 1 + block_types["image_page"]
    scores["analysis_only"] += 1
    summary_options = _summary_table_options(ai_summary)
    catalog = _catalog_options(db, text, fragments)
    ranked = _options(TABLE_OPTIONS, scores, TABLE_SIGNALS, fragments, "deterministic_router")
    return _dedupe_options(summary_options + catalog + ranked)[:6]


def _summary_table_options(ai_summary: dict | None) -> list[dict]:
    candidates = (ai_summary or {}).get("table_candidates") or []
    if not isinstance(candidates, list):
        return []
    rows = []
    for item in candidates[:4]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("table_name", "")).replace("new_table:", "").strip()
        if not name:
            continue
        reason = str(item.get("reason", "Gemma summary candidate"))
        rows.append({
            "value": name,
            "label": name,
            "confidence": 0.9,
            "reason": reason,
            "source": "gemma_summary",
            "evidence": [],
        })
    return rows


def _catalog_options(db: Session, text: str, fragments: list[str]) -> list[dict]:
    rows = db.query(TableCatalog).order_by(TableCatalog.updated_at.desc()).limit(30).all()
    options = []
    for row in rows:
        haystack = f"{row.table_name} {row.description}".lower()
        words = [part for part in haystack.replace("_", " ").split() if len(part) > 3]
        score = _hit_score(text, words)
        confidence = round(min(0.95, 0.45 + 0.08 * score), 2)
        options.append({
            "value": row.table_name,
            "label": f"{row.schema_name}.{row.table_name}",
            "confidence": confidence,
            "connection_id": row.connection_id,
            "schema_name": row.schema_name,
            "reason": row.description or "Known catalog table.",
            "source": "table_catalog",
            "signals": _matched_words(text, words),
            "evidence": _evidence(fragments, words),
        })
    return sorted(options, key=lambda item: item["confidence"], reverse=True)[:4]


def _options(
    labels: list[tuple[str, str]],
    scores: dict[str, int],
    signal_map: dict[str, list[str]],
    fragments: list[str],
    source: str,
) -> list[dict]:
    best = max(max(scores.values()), 1)
    rows = []
    for value, label in labels:
        score = scores.get(value, 0)
        confidence = round(min(0.95, 0.25 + 0.7 * score / best), 2)
        signals = _matched_words("\n".join(fragments).lower(), signal_map.get(value, []))
        rows.append({
            "value": value,
            "label": label,
            "confidence": confidence,
            "reason": _option_reason(label, signals, score),
            "signals": signals,
            "evidence": _evidence(fragments, signal_map.get(value, [])),
            "source": source,
        })
    return sorted(rows, key=lambda item: item["confidence"], reverse=True)[:4]


def _dedupe_options(options: list[dict]) -> list[dict]:
    seen = set()
    rows = []
    for option in options:
        key = option.get("value")
        if key in seen:
            continue
        seen.add(key)
        rows.append(option)
    return rows


def _summary_text(ai_summary: dict | None) -> list[str]:
    if not ai_summary:
        return []
    parts = [str(ai_summary.get("summary", ""))]
    for key in ("key_points", "quality_notes"):
        value = ai_summary.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return parts


def _hits(text: str, words: list[str]) -> int:
    return sum(1 for word in words if word in text)


def _hit_score(text: str, words: list[str]) -> int:
    return sum(min(8, len(re.findall(re.escape(word.lower()), text))) for word in words if word)


def _matched_words(text: str, words: list[str]) -> list[str]:
    return [word for word in words if word.lower() in text][:8]


def _evidence(fragments: list[str], words: list[str]) -> list[str]:
    rows = []
    lowered_words = [word.lower() for word in words if word]
    for fragment in fragments:
        clean = " ".join(fragment.split())
        lower = clean.lower()
        if clean and any(word in lower for word in lowered_words):
            rows.append(clean[:220])
        if len(rows) >= 3:
            break
    return rows


def _option_reason(label: str, signals: list[str], score: int) -> str:
    if signals:
        return f"{label}: matched {len(signals)} signal(s), score {score}."
    return f"{label}: weak fallback option, score {score}."


def _reason(confidence: float, doc_options: list[dict], table_options: list[dict], block_types: Counter) -> str:
    if confidence < 0.78:
        return "Document type or target table is ambiguous; user choice is required."
    doc = doc_options[0]["label"]
    table = table_options[0]["value"]
    return f"Suggested {doc} -> {table}; extracted block profile: {dict(block_types)}."
