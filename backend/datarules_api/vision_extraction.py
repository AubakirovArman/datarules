from collections.abc import Callable
from typing import Any

from .llm.vision import extract_page_image_sync
from .parsers.common import CanonicalBlock, clean_text

VisionExtractor = Callable[[str, int | None], dict[str, Any]]


def enrich_image_pages(
    blocks: list[CanonicalBlock],
    extractor: VisionExtractor = extract_page_image_sync,
) -> list[CanonicalBlock]:
    enriched: list[CanonicalBlock] = []
    for block in blocks:
        enriched.append(block)
        if block.block_type != "image_page":
            continue
        image_path = str((block.metadata or {}).get("image_path") or "")
        if not image_path:
            continue
        result = extractor(image_path, block.page)
        block.metadata = {
            **(block.metadata or {}),
            "vision_source": result.get("source"),
            "vision_quality_notes": result.get("quality_notes", []),
        }
        enriched.extend(_summary_blocks(block, result, image_path))
        enriched.extend(_text_blocks(block, result, image_path))
        enriched.extend(_table_blocks(block, result, image_path))
    return enriched


def _summary_blocks(parent: CanonicalBlock, result: dict[str, Any], image_path: str) -> list[CanonicalBlock]:
    summary = clean_text(str(result.get("page_summary") or "")).strip()
    if not summary:
        return []
    return [
        CanonicalBlock(
            block_type="paragraph",
            page=parent.page,
            text=summary,
            confidence=0.72,
            metadata=_metadata("page_summary", image_path, result),
        )
    ]


def _text_blocks(parent: CanonicalBlock, result: dict[str, Any], image_path: str) -> list[CanonicalBlock]:
    rows = []
    for item in result.get("blocks", []):
        if not isinstance(item, dict):
            continue
        text = clean_text(str(item.get("text") or "")).strip()
        if not text:
            continue
        rows.append(
            CanonicalBlock(
                block_type=str(item.get("type") or "paragraph")[:40],
                page=parent.page,
                text=text,
                confidence=_confidence(item.get("confidence"), 0.74),
                metadata=_metadata("text_block", image_path, result),
            )
        )
    return rows


def _table_blocks(parent: CanonicalBlock, result: dict[str, Any], image_path: str) -> list[CanonicalBlock]:
    rows = []
    for item in result.get("tables", []):
        if not isinstance(item, dict) or not isinstance(item.get("rows"), list):
            continue
        table_rows = item["rows"]
        text = "\n".join(" | ".join(map(str, row)) for row in table_rows[:30] if isinstance(row, list))
        rows.append(
            CanonicalBlock(
                block_type="table",
                page=parent.page,
                text=clean_text(text),
                table_json={"rows": table_rows},
                confidence=_confidence(item.get("confidence"), 0.72),
                metadata=_metadata("table_block", image_path, result),
            )
        )
    return rows


def _metadata(kind: str, image_path: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "gemma4_vision",
        "kind": kind,
        "image_path": image_path,
        "quality_notes": result.get("quality_notes", []),
    }


def _confidence(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
