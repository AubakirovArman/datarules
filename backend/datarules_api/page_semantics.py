from collections import defaultdict

from .models import DocumentBlock
from .schemas import PageSummary


def page_summaries(blocks: list[DocumentBlock], ai_summary: dict | None = None) -> list[PageSummary]:
    grouped: dict[str, list[DocumentBlock]] = defaultdict(list)
    semantic = _semantic_map(ai_summary)
    for block in blocks:
        grouped[_block_label(block)].append(block)
    return [
        PageSummary(
            label=label,
            blocks=len(items),
            tables=sum(1 for item in items if item.block_type == "table"),
            text_chars=sum(len(item.text or "") for item in items),
            low_confidence_blocks=sum(1 for item in items if item.confidence < 0.75),
            semantic_summary=semantic.get(label) or _extractive_page_summary(items),
        )
        for label, items in sorted(grouped.items())
    ]


def _semantic_map(ai_summary: dict | None) -> dict[str, str]:
    rows = (ai_summary or {}).get("page_summaries")
    if not isinstance(rows, list):
        return {}
    result = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        summary = str(item.get("summary") or item.get("semantic_summary") or "").strip()
        if label and summary:
            result[label] = summary[:360]
    return result


def _extractive_page_summary(blocks: list[DocumentBlock]) -> str:
    page_summary = _metadata_page_summary(blocks)
    if page_summary:
        return page_summary
    texts = [_clean(block.text) for block in blocks if block.text and block.block_type != "image_page"]
    ranked = sorted(texts, key=lambda text: (_signal_score(text), len(text)), reverse=True)
    return (ranked[0] if ranked else "")[:360]


def _metadata_page_summary(blocks: list[DocumentBlock]) -> str:
    for block in blocks:
        table_json = block.table_json if isinstance(block.table_json, dict) else {}
        metadata = table_json.get("metadata") if isinstance(table_json.get("metadata"), dict) else {}
        if metadata.get("kind") == "page_summary" and block.text:
            return _clean(block.text)[:360]
    return ""


def _signal_score(text: str) -> int:
    lower = text.lower()
    words = ("проект", "инвест", "решени", "сумм", "срок", "risk", "capex", "жоба", "қаржы")
    return sum(1 for word in words if word in lower)


def _clean(text: str | None) -> str:
    return " ".join(str(text or "").split())


def _block_label(block: DocumentBlock) -> str:
    if block.page is not None:
        return f"page {block.page}"
    if block.sheet_name:
        return f"sheet {block.sheet_name}"
    if block.slide_number is not None:
        return f"slide {block.slide_number}"
    return "document"
