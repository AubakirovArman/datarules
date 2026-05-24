import re
from typing import Any

from .schemas import AskCitation

STOPWORDS = {"what", "which", "where", "when", "with", "about", "что", "где", "как", "когда", "меня", "үшін"}


def retrieval_quality_gate(query: str, citations: list[AskCitation]) -> dict[str, Any]:
    if not citations:
        return _gate("blocked", ["no_sources"], {"citations": 0})
    terms = _query_terms(query)
    matched = _matched_terms(citations)
    best_score = max(float(item.score or 0.0) for item in citations)
    coverage = len(set(matched)) / max(len(terms), 1) if terms else 1.0
    semantic = _has_semantic(citations)
    reasons: list[str] = []
    warnings: list[str] = []
    if best_score < 0.08:
        reasons.append("retrieval_score_too_low")
    if terms and coverage == 0 and not semantic:
        reasons.append("no_query_terms_matched")
    if len(citations) < 2:
        warnings.append("single_source_answer")
    if not _has_provenance(citations):
        warnings.append("weak_source_provenance")
    if best_score < 0.2:
        warnings.append("low_retrieval_score")
    status = "blocked" if reasons else "warning" if warnings else "passed"
    return _gate(status, reasons or warnings, {
        "citations": len(citations),
        "best_score": round(best_score, 6),
        "query_terms": terms,
        "matched_terms": sorted(set(matched)),
        "term_coverage": round(coverage, 4),
        "semantic_evidence": semantic,
        "sources": _sources(citations),
    })


def answer_quality_gate(grounding: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    warnings = []
    if grounding.get("invalid_markers"):
        reasons.append("invalid_citation_markers")
    if not grounding.get("valid_markers"):
        reasons.append("no_valid_citation_markers")
    try:
        coverage = float(grounding.get("coverage") or 0)
    except (TypeError, ValueError):
        coverage = 0.0
    if coverage < 0.5:
        reasons.append("low_citation_coverage")
    if grounding.get("status") == "markers_added":
        warnings.append("markers_added_by_guard")
    status = "blocked" if reasons else "warning" if warnings else "passed"
    return _gate(status, reasons or warnings, {"coverage": round(coverage, 4)})


def combined_quality_gate(retrieval: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    status = "passed"
    if "blocked" in {retrieval.get("status"), answer.get("status")}:
        status = "blocked"
    elif "warning" in {retrieval.get("status"), answer.get("status")}:
        status = "warning"
    return {
        "status": status,
        "reasons": [*_reasons(retrieval), *_reasons(answer)],
        "retrieval": retrieval,
        "answer": answer,
    }


def quality_confidence(base: str, quality: dict[str, Any]) -> str:
    if quality.get("status") == "blocked":
        return "low"
    if quality.get("status") == "warning" and base == "high":
        return "medium"
    return base


def insufficient_answer(query: str, quality: dict[str, Any]) -> str:
    reasons = ", ".join(str(item) for item in quality.get("reasons", [])[:4]) or "weak_evidence"
    lang = _language(query)
    if lang == "kk":
        return f"Бұл сұраққа сенімді жауап беру үшін расталған дерек жеткіліксіз. Себеп: {reasons}. Маршрутты, индекстерді немесе сұрақты нақтылаңыз."
    if lang == "en":
        return f"I do not have enough grounded evidence to answer this safely. Reason: {reasons}. Check routing, indexes, or refine the question."
    return f"Недостаточно подтверждённых источников, чтобы безопасно ответить. Причина: {reasons}. Проверьте маршрутизацию, индексы или уточните вопрос."


def _gate(status: str, reasons: list[str], metrics: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "reasons": reasons, "metrics": metrics}


def _query_terms(query: str) -> list[str]:
    terms = []
    for term in re.findall(r"[0-9A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі_-]{3,}", query.lower()):
        if term not in STOPWORDS and term not in terms:
            terms.append(term)
    return terms[:10]


def _matched_terms(citations: list[AskCitation]) -> list[str]:
    rows = []
    for item in citations:
        rerank = item.metadata.get("rerank") if isinstance(item.metadata.get("rerank"), dict) else {}
        rows.extend(str(term) for term in rerank.get("matched_terms", []) if term)
    return rows


def _has_semantic(citations: list[AskCitation]) -> bool:
    for item in citations:
        fusion = item.metadata.get("fusion") if isinstance(item.metadata.get("fusion"), dict) else {}
        sources = fusion.get("sources") if isinstance(fusion.get("sources"), list) else []
        if item.match_source == "semantic_vector" or "semantic_vector" in sources:
            return True
    return False


def _has_provenance(citations: list[AskCitation]) -> bool:
    return any(item.block_id and (item.page is not None or item.sheet_name or item.metadata.get("field_sources")) for item in citations)


def _sources(citations: list[AskCitation]) -> list[str]:
    return sorted({str(item.match_source or item.block_type) for item in citations})


def _reasons(gate: dict[str, Any]) -> list[str]:
    return [str(item) for item in gate.get("reasons", [])]


def _language(query: str) -> str:
    text = query.lower()
    if any(char in text for char in "әғқңөұүһі"):
        return "kk"
    if any("а" <= char <= "я" for char in text):
        return "ru"
    return "en"
