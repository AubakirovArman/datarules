import base64
import io
import json
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from ..config import get_settings


def extract_page_image_sync(image_path: str, page: int | None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.enable_gemma_calls or not settings.gemma_base_url:
        return {"source": "gemma_disabled", "blocks": [], "quality_notes": ["Gemma vision is disabled."]}
    payload = {
        "model": settings.gemma_model_id,
        "temperature": 0.0,
        "max_tokens": 1600,
        "messages": [
            {"role": "system", "content": _prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze scanned document page {page or ''}."},
                    {"type": "image_url", "image_url": {"url": _data_url(Path(image_path))}},
                ],
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.gemma_api_key}"}
    try:
        url = settings.gemma_base_url.rstrip("/") + "/chat/completions"
        with httpx.Client(timeout=settings.gemma_timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return _normalize(_json_from_content(content))
    except (httpx.HTTPError, KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"source": "gemma4_vision_error", "blocks": [], "quality_notes": [str(exc)]}


def _prompt() -> str:
    return (
        "You are DataRules OCR and layout analyst for scanned document pages. "
        "Return only valid JSON with keys page_summary, blocks, tables, quality_notes. "
        "Preserve visible text exactly when possible. Do not invent missing values. "
        "blocks: max 12 objects with type paragraph/key_value, text, confidence. "
        "tables: max 4 objects with rows as a 2D string array, confidence. "
        "If the page is unreadable, return empty blocks and explain in quality_notes. "
        "Use the same language as the document image."
    )


def _data_url(path: Path) -> str:
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((1800, 1800))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def _json_from_content(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.removeprefix("json").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


def _normalize(value: dict[str, Any]) -> dict[str, Any]:
    blocks = value.get("blocks")
    tables = value.get("tables")
    notes = value.get("quality_notes")
    return {
        "source": "gemma4_vision",
        "page_summary": str(value.get("page_summary") or ""),
        "blocks": blocks[:12] if isinstance(blocks, list) else [],
        "tables": tables[:4] if isinstance(tables, list) else [],
        "quality_notes": notes[:8] if isinstance(notes, list) else [],
    }
