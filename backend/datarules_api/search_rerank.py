import re
from typing import Any

from .schemas import SearchHit

STOPWORDS = {"what", "which", "where", "when", "with", "about", "что", "где", "как", "когда", "үшін"}


def rerank_hits(query: str, hits: list[SearchHit], limit: int) -> list[SearchHit]:
    terms = _query_terms(query)
    rows = [_reranked_hit(query, terms, hit) for hit in hits]
    return sorted(rows, key=lambda item: item.score, reverse=True)[:limit]


def _reranked_hit(query: str, terms: list[str], hit: SearchHit) -> SearchHit:
    haystack = _haystack(hit)
    matched = [term for term in terms if term in haystack]
    lexical = len(matched) / max(len(terms), 1)
    phrase = _clean(query) in haystack if query.strip() else False
    provenance = _provenance_score(hit)
    confidence = _confidence(hit)
    penalty = _penalty(hit)
    score_before = float(hit.score or 0.0)
    score_after = score_before + lexical * 0.35 + (0.18 if phrase else 0) + provenance * 0.08 + confidence * 0.04 - penalty
    metadata = {
        **(hit.metadata or {}),
        "rerank": {
            "method": "deterministic_v1",
            "query_terms": terms,
            "matched_terms": matched,
            "lexical_score": round(lexical, 4),
            "phrase_match": phrase,
            "provenance_score": round(provenance, 4),
            "confidence": round(confidence, 4),
            "penalty": round(penalty, 4),
            "score_before": round(score_before, 6),
            "score_after": round(score_after, 6),
        },
    }
    return hit.model_copy(update={"score": round(score_after, 6), "metadata": metadata})


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for term in re.findall(r"[0-9A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі_-]{3,}", query.lower()):
        if term not in STOPWORDS and term not in terms:
            terms.append(term)
    return terms[:10]


def _haystack(hit: SearchHit) -> str:
    metadata = hit.metadata or {}
    field_values = metadata.get("field_values") if isinstance(metadata.get("field_values"), dict) else {}
    parts = [
        hit.text,
        hit.file_name,
        hit.target_table or "",
        " ".join(str(value) for value in field_values.values()),
    ]
    return _clean(" ".join(parts))


def _provenance_score(hit: SearchHit) -> float:
    metadata = hit.metadata or {}
    sources = metadata.get("field_sources") if isinstance(metadata.get("field_sources"), dict) else {}
    if sources:
        return 1.0
    if hit.block_id and (hit.page is not None or hit.sheet_name):
        return 0.75
    return 0.35 if hit.block_id else 0.0


def _confidence(hit: SearchHit) -> float:
    value = (hit.metadata or {}).get("source_confidence")
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.7 if hit.block_type == "agent_chunk" else 0.55


def _penalty(hit: SearchHit) -> float:
    errors = (hit.metadata or {}).get("validation_errors")
    return 0.08 if isinstance(errors, list) and errors else 0.0


def _clean(value: Any) -> str:
    return " ".join(str(value or "").lower().split())
