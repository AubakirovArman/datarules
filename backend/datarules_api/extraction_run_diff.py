from typing import Any

from .extraction_runs import load_run_snapshot, run_to_dict
from .models import DocumentExtractionRun


def diff_extraction_runs(left: DocumentExtractionRun, right: DocumentExtractionRun) -> dict[str, Any]:
    left_snapshot = load_run_snapshot(left)
    right_snapshot = load_run_snapshot(right)
    left_blocks = _blocks(left_snapshot)
    right_blocks = _blocks(right_snapshot)
    changes = _block_changes(left_blocks, right_blocks)
    return {
        "from_run": run_to_dict(left),
        "against_run": run_to_dict(right),
        "summary": _summary(left_blocks, right_blocks, changes),
        "metrics_delta": _delta(left.metrics_json or {}, right.metrics_json or {}),
        "quality_delta": _delta(left.quality_json or {}, right.quality_json or {}),
        "changed_blocks": changes["changed"][:30],
        "added_blocks": changes["added"][:20],
        "removed_blocks": changes["removed"][:20],
    }


def _blocks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in snapshot.get("blocks") or [] if isinstance(item, dict)]


def _block_changes(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    left_index = {_key(index, block): block for index, block in enumerate(left)}
    right_index = {_key(index, block): block for index, block in enumerate(right)}
    added = [_block_note(key, right_index[key], "added") for key in sorted(right_index.keys() - left_index.keys())]
    removed = [_block_note(key, left_index[key], "removed") for key in sorted(left_index.keys() - right_index.keys())]
    changed = []
    for key in sorted(left_index.keys() & right_index.keys()):
        before = left_index[key]
        after = right_index[key]
        if _fingerprint(before) != _fingerprint(after):
            changed.append(_change_note(key, before, after))
    return {"added": added, "removed": removed, "changed": changed}


def _summary(left: list[dict[str, Any]], right: list[dict[str, Any]], changes: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "from_blocks": len(left),
        "against_blocks": len(right),
        "added_blocks": len(changes["added"]),
        "removed_blocks": len(changes["removed"]),
        "changed_blocks": len(changes["changed"]),
        "unchanged_blocks": max(0, min(len(left), len(right)) - len(changes["changed"])),
        "from_pages": sorted(_pages(left)),
        "against_pages": sorted(_pages(right)),
        "added_pages": sorted(_pages(right) - _pages(left)),
        "removed_pages": sorted(_pages(left) - _pages(right)),
    }


def _delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    rows = {}
    for key in sorted(set(left) | set(right)):
        if isinstance(left.get(key), (int, float)) and isinstance(right.get(key), (int, float)):
            rows[key] = round(float(right[key]) - float(left[key]), 4)
    return rows


def _key(index: int, block: dict[str, Any]) -> str:
    page = block.get("page") if block.get("page") is not None else "-"
    sheet = block.get("sheet_name") or "-"
    slide = block.get("slide_number") if block.get("slide_number") is not None else "-"
    kind = block.get("type") or block.get("block_type") or "block"
    return f"{index:05d}|p:{page}|s:{sheet}|sl:{slide}|t:{kind}"


def _fingerprint(block: dict[str, Any]) -> tuple[Any, ...]:
    return (
        block.get("type") or block.get("block_type"),
        _text(block),
        block.get("table_json"),
        round(float(block.get("confidence") or 0), 4),
    )


def _change_note(key: str, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "location": _location(after or before),
        "block_type": after.get("type") or before.get("type") or "",
        "before_text": _clip(_text(before)),
        "after_text": _clip(_text(after)),
        "before_confidence": before.get("confidence"),
        "after_confidence": after.get("confidence"),
        "text_delta": len(_text(after)) - len(_text(before)),
    }


def _block_note(key: str, block: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "location": _location(block),
        "block_type": block.get("type") or block.get("block_type") or "",
        "text": _clip(_text(block)),
        "confidence": block.get("confidence"),
    }


def _location(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": block.get("page"),
        "sheet_name": block.get("sheet_name"),
        "slide_number": block.get("slide_number"),
    }


def _pages(blocks: list[dict[str, Any]]) -> set[int]:
    return {int(block["page"]) for block in blocks if isinstance(block.get("page"), int)}


def _text(block: dict[str, Any]) -> str:
    return str(block.get("text") or "")


def _clip(value: str, limit: int = 320) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
