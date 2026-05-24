from collections import Counter
from typing import Any

from .models import DocumentBlock


def build_quality_profile(blocks: list[DocumentBlock]) -> dict[str, Any]:
    counts = Counter(block.block_type for block in blocks)
    total = len(blocks)
    low_confidence = sum(1 for block in blocks if block.confidence < 0.75)
    empty_blocks = sum(1 for block in blocks if _empty(block))
    text_chars = sum(len(block.text or "") for block in blocks)
    pages = {block.page for block in blocks if block.page is not None}
    pages_with_text = {block.page for block in blocks if block.page is not None and (block.text or "").strip()}
    avg_confidence = round(sum(block.confidence for block in blocks) / total, 3) if total else 0.0
    score = _score(total, text_chars, low_confidence, empty_blocks, counts["image_page"])
    return {
        "status": _status(score, total, text_chars),
        "extraction_score": score,
        "average_confidence": avg_confidence,
        "low_confidence_blocks": low_confidence,
        "empty_blocks": empty_blocks,
        "image_pages_pending": counts["image_page"],
        "table_blocks": counts["table"],
        "text_chars": text_chars,
        "total_pages": len(pages),
        "pages_with_text": len(pages_with_text),
        "warnings": _warnings(total, text_chars, low_confidence, empty_blocks, counts["image_page"]),
    }


def quality_load_issues(document_id: str, file_name: str, quality: dict[str, Any]) -> list[dict[str, Any]]:
    status = quality.get("status")
    if status == "blocked":
        return [{
            "severity": "error",
            "code": "document_quality_blocked",
            "document_id": document_id,
            "file_name": file_name,
            "message": "Document extraction quality is too low for trusted loading.",
        }]
    if status == "needs_review":
        return [{
            "severity": "warning",
            "code": "document_quality_review",
            "document_id": document_id,
            "file_name": file_name,
            "message": "Document extraction quality needs human review before loading.",
        }]
    return []


def quality_action_keys(quality: dict[str, Any]) -> list[str]:
    warnings = quality.get("warnings") if isinstance(quality.get("warnings"), list) else []
    keys = {str(item.get("key")) for item in warnings if isinstance(item, dict)}
    actions = []
    if "no_blocks" in keys or "no_text" in keys:
        actions.append("rerun_extraction")
    if "image_pages" in keys:
        actions.append("review_ocr")
    if "low_confidence" in keys:
        actions.append("review_low_confidence")
    if "empty_blocks" in keys:
        actions.append("inspect_empty_blocks")
    return actions or ["ready_for_routing"]


def _score(total: int, text_chars: int, low_confidence: int, empty_blocks: int, image_pages: int) -> int:
    if total == 0:
        return 0
    score = 100
    if text_chars == 0:
        score -= 45
    elif text_chars < 250:
        score -= 20
    score -= min(35, round((low_confidence / total) * 100))
    score -= min(20, round((empty_blocks / total) * 60))
    score -= min(40, image_pages * 20)
    return max(0, min(100, score))


def _status(score: int, total: int, text_chars: int) -> str:
    if total == 0 or text_chars == 0 or score < 45:
        return "blocked"
    if score < 80:
        return "needs_review"
    return "ready"


def _warnings(
    total: int,
    text_chars: int,
    low_confidence: int,
    empty_blocks: int,
    image_pages: int,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if total == 0:
        warnings.append({"key": "no_blocks", "severity": "error", "count": 0})
    if text_chars == 0:
        warnings.append({"key": "no_text", "severity": "error", "count": 0})
    if image_pages:
        warnings.append({"key": "image_pages", "severity": "warning", "count": image_pages})
    if low_confidence:
        warnings.append({"key": "low_confidence", "severity": "warning", "count": low_confidence})
    if empty_blocks:
        warnings.append({"key": "empty_blocks", "severity": "warning", "count": empty_blocks})
    return warnings


def _empty(block: DocumentBlock) -> bool:
    return not (block.text or "").strip() and not block.table_json
