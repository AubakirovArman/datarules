from datetime import datetime
from typing import Any

from .schemas import AskResponse


def evaluate_golden_answer(answer: AskResponse, expected_terms: list[str]) -> dict[str, Any]:
    terms = _clean_terms(expected_terms)
    haystack = _haystack(answer)
    matched = [term for term in terms if term.lower() in haystack]
    missing = [term for term in terms if term not in matched]
    grounding = answer.grounding or {}
    gate = grounding.get("quality_gate") if isinstance(grounding.get("quality_gate"), dict) else {}
    base_score = _term_score(terms, matched)
    source_bonus = 20 if answer.citations else 0
    gate_penalty = 35 if gate.get("status") == "blocked" else 0
    confidence_penalty = 15 if answer.confidence == "low" else 0
    score = max(0, min(100, base_score + source_bonus - gate_penalty - confidence_penalty))
    return {
        "status": _status(score, missing, answer, gate),
        "score": score,
        "expected_terms": terms,
        "matched_terms": matched,
        "missing_terms": missing,
        "answer": answer.answer,
        "confidence": answer.confidence,
        "model_source": answer.model_source,
        "citation_count": len(answer.citations),
        "grounding_status": grounding.get("status"),
        "quality_gate": gate,
        "ran_at": datetime.utcnow().isoformat(),
    }


def _clean_terms(value: list[str]) -> list[str]:
    return [term.strip() for term in value if isinstance(term, str) and term.strip()][:20]


def _haystack(answer: AskResponse) -> str:
    parts = [answer.answer]
    parts.extend(citation.text for citation in answer.citations)
    return "\n".join(parts).lower()


def _term_score(terms: list[str], matched: list[str]) -> int:
    if not terms:
        return 45
    return round(len(matched) / len(terms) * 80)


def _status(score: int, missing: list[str], answer: AskResponse, gate: dict[str, Any]) -> str:
    if not answer.citations or gate.get("status") == "blocked":
        return "blocked"
    if missing:
        return "fail"
    return "pass" if score >= 75 else "fail"
