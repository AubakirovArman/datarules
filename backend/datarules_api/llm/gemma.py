import json
from typing import Any

import httpx

from ..config import Settings, get_settings
from .prompts import SCHEMA_PROMPT

SUMMARY_PROMPT_VERSION = "gemma4_document_summary_v4"
ENGLISH_MARKERS = {"the", "document", "project", "investment", "contains", "summary", "reported", "total"}


class GemmaClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def propose_schema_sync(self, snippets: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.settings.enable_gemma_calls or not self.settings.gemma_base_url:
            return self._fallback_schema(snippets)

        payload = {
            "model": self.settings.gemma_model_id,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SCHEMA_PROMPT},
                {"role": "user", "content": json.dumps(snippets[:80], ensure_ascii=False)},
            ],
        }
        url = self.settings.gemma_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.gemma_api_key}"}

        try:
            with httpx.Client(timeout=self.settings.gemma_timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            fallback = self._fallback_schema(snippets)
            fallback["llm_error"] = str(exc)
            return fallback

        return self._json_or_fallback(content, snippets)

    def summarize_document_sync(self, document: dict[str, Any], snippets: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.settings.enable_gemma_calls or not self.settings.gemma_base_url:
            return self._fallback_document_summary(document, snippets)
        payload = {
            "model": self.settings.gemma_model_id,
            "temperature": 0.1,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": _document_summary_prompt()},
                {
                    "role": "user",
                    "content": json.dumps({"document": document, "snippets": snippets[:90]}, ensure_ascii=False),
                },
            ],
        }
        url = self.settings.gemma_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.gemma_api_key}"}
        try:
            expected_language = str(document.get("language_hint") or "")
            with httpx.Client(timeout=self.settings.gemma_timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                summary = _normalize_document_summary(_json_from_content(content), "gemma4", expected_language)
                if _language_mismatch(summary, expected_language):
                    summary = _rewrite_summary_language(client, url, headers, summary, expected_language) or summary
            if _language_mismatch(summary, expected_language):
                summary["quality_notes"] = [
                    *_list(summary.get("quality_notes"), 3),
                    "Summary language did not match the detected document language; review recommended.",
                ]
            return summary
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
            fallback = self._fallback_document_summary(document, snippets)
            fallback["llm_error"] = str(exc)
            return fallback

    def _json_or_fallback(self, content: str, snippets: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    pass
        fallback = self._fallback_schema(snippets)
        fallback["llm_raw_response"] = content[:4000]
        return fallback

    def _fallback_schema(self, snippets: list[dict[str, Any]]) -> dict[str, Any]:
        block_types = sorted({str(item.get("block_type", "unknown")) for item in snippets})
        files = sorted({str(item.get("file_name", "unknown")) for item in snippets})
        return {
            "dataset_summary": f"Dataset contains {len(files)} file(s) with {len(snippets)} blocks.",
            "tables": [
                {
                    "name": "records",
                    "purpose": "Universal normalized records before user-approved physical tables.",
                    "columns": [
                        {"name": "record_id", "type": "text", "required": True},
                        {"name": "entity_name", "type": "text", "required": False},
                        {"name": "amount", "type": "decimal", "required": False},
                        {"name": "currency", "type": "text", "required": False},
                        {"name": "date", "type": "date", "required": False},
                        {"name": "source_document_id", "type": "text", "required": True},
                        {"name": "source_block_id", "type": "text", "required": True},
                        {"name": "confidence", "type": "float", "required": True},
                    ],
                }
            ],
            "quality_checks": [
                "Every extracted value must keep source_document_id and source_block_id.",
                "Dates, currencies, and amounts require deterministic validation.",
                "Low-confidence image_page blocks require multimodal Gemma/OCR review.",
            ],
            "query_guide": {
                "sql_examples": ["select * from records where currency = 'USD'"],
                "search_examples": ["Find mentions of CAPEX", "Find renewable energy projects"],
                "filters": ["file_name", "block_type", *block_types],
            },
            "mode": "fallback_without_live_gemma",
        }

    def _fallback_document_summary(self, document: dict[str, Any], snippets: list[dict[str, Any]]) -> dict[str, Any]:
        text = "\n".join(str(item.get("text", "")) for item in snippets[:8])
        return {
            "source": "fallback_without_live_gemma",
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "language": document.get("language_hint", "ru"),
            "summary": _fallback_summary_text(document, snippets),
            "key_points": [line[:220] for line in text.splitlines() if line.strip()][:5],
            "entities": [],
            "table_candidates": [{"table_name": "documents_raw", "reason": _fallback_reason(document)}],
            "page_summaries": [],
            "quality_notes": [_fallback_note(document)],
        }


def _document_summary_prompt() -> str:
    return (
        "You are DataRules Gemma4 document analyst. Return only valid JSON. "
        "Use the document language from language_hint for every human-readable value. "
        "If language_hint is ru, write Russian only; if kk, write Kazakh only; if en, write English only. "
        "Keep database identifiers, company names, file names, currencies, and source terms unchanged. "
        "Keys: language, summary, key_points, entities, table_candidates, page_summaries, quality_notes. "
        "summary: 2-4 concise sentences about document meaning, not parser statistics. "
        "key_points: max 5 short bullets. "
        "entities: max 8 objects with name, type, value_or_role. "
        "table_candidates: max 4 database-table candidates only, objects with table_name and reason. "
        "page_summaries: max 8 objects with label like 'page 1' and a short semantic summary. "
        "Allowed table_name examples: investment_projects, project_financials, project_milestones, "
        "companies, documents_raw, or new_table:<safe_name>. "
        "Do not put ministries, banks, people, or companies into table_candidates unless they are the table subject. "
        "quality_notes: max 4 notes about missing/ambiguous data. Do not invent facts."
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


def _normalize_document_summary(value: dict[str, Any], source: str, expected_language: str = "") -> dict[str, Any]:
    return {
        "source": source,
        "prompt_version": SUMMARY_PROMPT_VERSION,
        "language": str(value.get("language") or expected_language),
        "summary": str(value.get("summary") or ""),
        "key_points": _list(value.get("key_points"), 5),
        "entities": _list(value.get("entities"), 8),
        "table_candidates": _list(value.get("table_candidates") or value.get("recommended_destinations"), 4),
        "page_summaries": _list(value.get("page_summaries"), 8),
        "quality_notes": _list(value.get("quality_notes"), 4),
    }


def _list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _rewrite_summary_language(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    summary: dict[str, Any],
    language: str,
) -> dict[str, Any] | None:
    payload = {
        "model": get_settings().gemma_model_id,
        "temperature": 0.0,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": _language_rewrite_prompt(language)},
            {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
        ],
    }
    try:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _normalize_document_summary(_json_from_content(content), "gemma4_language_rewrite", language)
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return None


def _language_rewrite_prompt(language: str) -> str:
    return (
        "Return only valid JSON with the same keys: language, summary, key_points, entities, "
        "table_candidates, page_summaries, quality_notes. Do not add facts. Translate or rewrite every human-readable "
        f"value into language '{language}'. Preserve table_name values and proper nouns."
    )


def _language_mismatch(summary: dict[str, Any], expected: str) -> bool:
    if expected not in {"ru", "kk"}:
        return False
    text = " " + _human_text(summary).lower() + " "
    markers = sum(1 for marker in ENGLISH_MARKERS if f" {marker} " in text)
    cyrillic = sum(1 for char in text if "а" <= char <= "я" or char in "әғқңөұүһі")
    latin = sum(1 for char in text if "a" <= char <= "z")
    return markers >= 2 and latin > cyrillic


def _human_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_human_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_human_text(item) for item in value)
    return str(value)


def _fallback_summary_text(document: dict[str, Any], snippets: list[dict[str, Any]]) -> str:
    lang = document.get("language_hint", "ru")
    name = document.get("file_name", "Document")
    if lang == "ru":
        return f"{name}: извлечено {len(snippets)} текстовых блоков. Смысловая сводка Gemma пока недоступна."
    if lang == "kk":
        return f"{name}: {len(snippets)} мәтін блогы алынды. Gemma мағыналық түйіндемесі әзірге қолжетімсіз."
    return f"{name}: extracted {len(snippets)} text blocks. Gemma semantic summary is not available yet."


def _fallback_reason(document: dict[str, Any]) -> str:
    lang = document.get("language_hint", "ru")
    if lang == "ru":
        return "Сохранить исходный текст до подтверждения схемы."
    if lang == "kk":
        return "Схема расталғанға дейін бастапқы мәтінді сақтау."
    return "Store source text before schema approval."


def _fallback_note(document: dict[str, Any]) -> str:
    lang = document.get("language_hint", "ru")
    if lang == "ru":
        return "Gemma summary недоступна; показана детерминированная сводка извлечения."
    if lang == "kk":
        return "Gemma түйіндемесі қолжетімсіз; детерминирленген шығару түйіндемесі көрсетілді."
    return "Gemma summary was not available; showing deterministic extraction summary."
