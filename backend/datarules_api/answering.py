import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .answer_grounding import guard_answer, guarded_confidence
from .answer_quality import (
    answer_quality_gate,
    combined_quality_gate,
    insufficient_answer,
    quality_confidence,
    retrieval_quality_gate,
)
from .config import get_settings
from .schemas import AskCitation, AskResponse, SearchRequest
from .search_routes import search_dataset

ANSWER_PROMPT_VERSION = "datarules_answer_v2"


def answer_dataset(db: Session, dataset_id: str, query: str, limit: int) -> AskResponse:
    settings = get_settings()
    hits = search_dataset(dataset_id, SearchRequest(query=query, limit=limit), db)
    citations = _citations(hits)
    retrieval_gate = retrieval_quality_gate(query, citations)
    if not citations:
        return AskResponse(
            answer=insufficient_answer(query, {"reasons": ["no_sources"]}),
            confidence="low",
            citations=[],
            retrieval_mode="hybrid_search",
            model_source="no_sources",
            prompt_version=ANSWER_PROMPT_VERSION,
            model_id=settings.gemma_model_id,
            grounding={"status": "no_sources", "valid_markers": [], "coverage": 0, "quality_gate": retrieval_gate},
        )
    if retrieval_gate["status"] == "blocked":
        return _blocked_response(query, citations, retrieval_gate, settings.gemma_model_id, "retrieval_quality_gate")
    answer, source = _ask_gemma(query, citations)
    if not answer:
        answer, source = _fallback_answer(query, citations), "extractive_fallback"
    answer, source, grounding = guard_answer(query, answer, citations, source)
    answer_gate = answer_quality_gate(grounding)
    quality_gate = combined_quality_gate(retrieval_gate, answer_gate)
    grounding["quality_gate"] = quality_gate
    if quality_gate["status"] == "blocked":
        answer = insufficient_answer(query, quality_gate)
        source = f"{source}_quality_gate"
    return AskResponse(
        answer=answer,
        confidence=quality_confidence(guarded_confidence(_confidence(citations), grounding), quality_gate),
        citations=citations,
        retrieval_mode="hybrid_search",
        model_source=source,
        prompt_version=ANSWER_PROMPT_VERSION,
        model_id=settings.gemma_model_id,
        grounding=grounding,
    )


def _blocked_response(query: str, citations: list[AskCitation], quality_gate: dict[str, Any], model_id: str, source: str) -> AskResponse:
    return AskResponse(
        answer=insufficient_answer(query, quality_gate),
        confidence="low",
        citations=citations,
        retrieval_mode="hybrid_search",
        model_source=source,
        prompt_version=ANSWER_PROMPT_VERSION,
        model_id=model_id,
        grounding={
            "status": "blocked_by_quality_gate",
            "available_markers": [item.marker for item in citations],
            "used_markers": [],
            "valid_markers": [],
            "invalid_markers": [],
            "coverage": 0,
            "quality_gate": quality_gate,
        },
    )


def _ask_gemma(query: str, citations: list[AskCitation]) -> tuple[str, str]:
    settings = get_settings()
    if not settings.enable_gemma_calls or not settings.gemma_base_url:
        return "", "gemma_disabled"
    payload = {
        "model": settings.gemma_model_id,
        "temperature": 0.05,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(_question_payload(query, citations), ensure_ascii=False)},
        ],
    }
    try:
        url = settings.gemma_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {settings.gemma_api_key}"}
        response = httpx.post(url, json=payload, headers=headers, timeout=settings.gemma_timeout_seconds)
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip(), "gemma4"
    except (httpx.HTTPError, KeyError, TypeError):
        return "", "gemma_error"


def _system_prompt() -> str:
    return (
        "You are DataRules answer agent. Answer in the user's language. "
        "Use only provided citations. If sources are insufficient, say that clearly. "
        "Cite claims with markers like [1], [2]. Do not invent facts."
    )


def _question_payload(query: str, citations: list[AskCitation]) -> dict[str, Any]:
    return {
        "question": query,
        "citations": [
            {
                "marker": item.marker,
                "file_name": item.file_name,
                "match_source": item.match_source,
                "page": item.page,
                "target_table": item.target_table,
                "score": item.score,
                "retrieval_trace": _trace(item.metadata),
                "text": item.text,
            }
            for item in citations
        ],
    }


def _citations(hits: list[Any]) -> list[AskCitation]:
    rows = []
    for index, hit in enumerate(hits[:8], start=1):
        rows.append(
            AskCitation(
                marker=f"[{index}]",
                document_id=hit.document_id,
                block_id=hit.block_id,
                file_name=hit.file_name,
                block_type=hit.block_type,
                page=hit.page,
                sheet_name=hit.sheet_name,
                target_table=hit.target_table,
                text=hit.text[:900],
                score=hit.score,
                match_source=hit.match_source,
                metadata=hit.metadata or {},
            )
        )
    return rows


def _trace(metadata: dict[str, Any]) -> dict[str, Any]:
    fusion = metadata.get("fusion") if isinstance(metadata.get("fusion"), dict) else {}
    rerank = metadata.get("rerank") if isinstance(metadata.get("rerank"), dict) else {}
    return {
        "fusion": {"method": fusion.get("method"), "sources": fusion.get("sources")},
        "rerank": {
            "matched_terms": rerank.get("matched_terms"),
            "provenance_score": rerank.get("provenance_score"),
        },
        "has_field_sources": isinstance(metadata.get("field_sources"), dict) and bool(metadata.get("field_sources")),
    }


def _fallback_answer(query: str, citations: list[AskCitation]) -> str:
    intro = f"По вопросу «{query}» найдены релевантные фрагменты, но live Gemma answer недоступен."
    lines = [intro]
    for item in citations[:3]:
        lines.append(f"{item.marker} {item.text[:260]}")
    return "\n".join(lines)


def _confidence(citations: list[AskCitation]) -> str:
    if not citations:
        return "low"
    best = max(item.score for item in citations)
    if best >= 1.2:
        return "high"
    if best >= 0.55:
        return "medium"
    return "low"
