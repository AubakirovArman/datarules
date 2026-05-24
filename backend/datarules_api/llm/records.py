import json
from typing import Any

import httpx

from ..config import get_settings


def extract_records_sync(
    document: dict[str, Any],
    target_schema: dict[str, Any],
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.enable_gemma_calls or not settings.gemma_base_url:
        return {"source": "fallback_without_live_gemma", "records": [], "quality_issues": []}

    payload = {
        "model": settings.gemma_model_id,
        "temperature": 0.05,
        "max_tokens": 1800,
        "messages": [
            {"role": "system", "content": _prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "document": document,
                        "target_schema": target_schema,
                        "snippets": snippets[:120],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.gemma_api_key}"}
    url = settings.gemma_base_url.rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=settings.gemma_timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return _normalize(_json_from_content(content), "gemma4")
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return {
            "source": "fallback_after_gemma_error",
            "records": [],
            "quality_issues": [{"severity": "warning", "message": str(exc)}],
        }


def _prompt() -> str:
    return (
        "You are DataRules structured extraction module. Return only valid JSON. "
        "Extract records for the selected database table from the provided document snippets. "
        "Never invent facts. If a value is not present, use null. "
        "Return keys: records, quality_issues. "
        "records: array of objects with row_label, field_values, content, "
        "source_block_id, field_sources, page, confidence, needs_review. "
        "field_values must use target_schema.target_columns names only. "
        "field_sources maps each non-null field to document_id, block_id, page, confidence, evidence. "
        "content is a concise human-readable row text for search/RAG. "
        "source_block_id must point to the strongest evidence snippet. "
        "quality_issues: array with severity and message. "
        "Keep the document language for text values."
    )


def _json_from_content(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


def _normalize(value: dict[str, Any], source: str) -> dict[str, Any]:
    records = value.get("records")
    issues = value.get("quality_issues")
    return {
        "source": source,
        "records": records[:30] if isinstance(records, list) else [],
        "quality_issues": issues[:20] if isinstance(issues, list) else [],
    }
