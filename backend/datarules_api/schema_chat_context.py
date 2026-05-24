from typing import Any

from .models import Dataset


def schema_chat_language(requested: str | None, summaries: list[dict[str, Any]]) -> str:
    if requested in {"ru", "kk", "en"}:
        return requested
    counts = {"ru": 0, "kk": 0, "en": 0}
    for row in summaries:
        summary = row.get("summary") if isinstance(row, dict) else {}
        language = str((summary or {}).get("language") or "")
        if language in counts:
            counts[language] += 1
    return max(counts, key=counts.get) if any(counts.values()) else "ru"


def schema_chat_usage(
    language: str,
    summaries: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "language": language,
        "document_summaries": len(summaries),
        "snippets": len(snippets),
        "known_tables": len(tables),
        "summary_first": True,
    }


def schema_chat_prompt(language: str) -> str:
    return (
        "You are a schema design assistant for DataRules. Return only JSON with keys "
        "assistant_message, table_name, columns, validation_rules, source_reference_policy, "
        "next_confirmation_step. Use document_summaries first, snippets only as evidence. "
        f"Write every human-readable value in language '{language}'. "
        "Keep database identifiers in safe snake_case. If the user asks for a new table, propose a safe schema. "
        "Never claim data is loaded; this is only a proposal for user confirmation."
    )


def fallback_chat_schema(dataset: Dataset, message: str, language: str) -> dict[str, Any]:
    table_name = "custom_projects" if _mentions_project(message) else "custom_records"
    return {
        "source": "fallback",
        "assistant_message": _message(dataset.name, language),
        "table_name": table_name,
        "columns": [
            {"name": "name", "type": "text", "required": False},
            {"name": "amount", "type": "decimal", "required": False},
            {"name": "currency", "type": "text", "required": False},
        ],
        "validation_rules": _rules(language),
        "source_reference_policy": _source_policy(language),
        "next_confirmation_step": _next_step(language),
    }


def _mentions_project(message: str) -> bool:
    lower = message.lower()
    return "project" in lower or "проект" in lower or "жоба" in lower


def _message(name: str, language: str) -> str:
    if language == "kk":
        return f"{name} үшін жаңа кесте ұсынылды. Жүктеу алдында схеманы растаңыз."
    if language == "en":
        return f"Proposed a new table for {name}. Confirm the schema before loading data."
    return f"Предложена новая таблица для {name}. Подтвердите схему перед загрузкой данных."


def _rules(language: str) -> list[str]:
    if language == "kk":
        return ["Дереккөз сілтемелері міндетті", "Сандар мен күндерді тексеру"]
    if language == "en":
        return ["Require source references", "Validate numbers and dates"]
    return ["Обязательны ссылки на источник", "Проверять числа и даты"]


def _source_policy(language: str) -> str:
    if language == "kk":
        return "Әр мән құжатқа, блокқа, бетке немесе ұяшыққа сілтенуі керек."
    if language == "en":
        return "Every value must point to a document and block, page, or cell."
    return "Каждое значение должно ссылаться на документ и блок, страницу или ячейку."


def _next_step(language: str) -> str:
    if language == "kk":
        return "Қолданушы кестеге жүктеу алдында схеманы бекітеді немесе түзетеді."
    if language == "en":
        return "User approves or edits the schema before table loading."
    return "Пользователь утверждает или редактирует схему перед загрузкой в таблицу."
