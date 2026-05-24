import re
from typing import Any

from .schemas import AskCitation


def guard_answer(query: str, answer: str, citations: list[AskCitation], source: str) -> tuple[str, str, dict[str, Any]]:
    markers = [item.marker for item in citations]
    used = _markers(answer)
    valid = [marker for marker in used if marker in markers]
    missing = [marker for marker in used if marker not in markers]
    status = "grounded" if valid and not missing else "needs_guard"
    guarded = answer
    if citations and not valid:
        valid = markers[: min(2, len(markers))]
        guarded = _append_sources(answer, valid, _language(query))
        status = "markers_added"
    grounding = {
        "status": status,
        "source": source,
        "available_markers": markers,
        "used_markers": used,
        "valid_markers": valid,
        "invalid_markers": missing,
        "coverage": _coverage(valid, markers),
    }
    return guarded, _guarded_source(source, status), grounding


def guarded_confidence(base: str, grounding: dict[str, Any]) -> str:
    if grounding.get("status") == "grounded" and base in {"high", "medium"}:
        return base
    if grounding.get("valid_markers"):
        return "medium" if base == "high" else base
    return "low"


def _markers(answer: str) -> list[str]:
    seen = []
    for marker in re.findall(r"\[\d+\]", answer):
        if marker not in seen:
            seen.append(marker)
    return seen


def _coverage(valid: list[str], markers: list[str]) -> float:
    required = max(1, min(len(markers), 2))
    return round(min(len(set(valid)), required) / required, 4)


def _append_sources(answer: str, markers: list[str], language: str) -> str:
    label = {"kk": "Дереккөздер", "en": "Sources"}.get(language, "Источники")
    clean = answer.strip()
    return f"{clean}\n\n{label}: {' '.join(markers)}" if clean else f"{label}: {' '.join(markers)}"


def _language(query: str) -> str:
    text = query.lower()
    if any(char in text for char in "әғқңөұүһі"):
        return "kk"
    if any("а" <= char <= "я" for char in text):
        return "ru"
    return "en"


def _guarded_source(source: str, status: str) -> str:
    return source if status == "grounded" else f"{source}_grounding_guard"
