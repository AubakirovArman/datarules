from types import SimpleNamespace

from datarules_api.answering import _citations, _question_payload


def test_answer_citations_preserve_retrieval_trace() -> None:
    hit = SimpleNamespace(
        document_id="doc1",
        block_id="blk1",
        file_name="source.txt",
        block_type="agent_chunk",
        page=1,
        sheet_name=None,
        target_table="projects",
        text="Project Alpha CAPEX 1200 USD",
        score=0.77,
        match_source="hybrid_rrf",
        metadata={
            "fusion": {"method": "rrf", "sources": ["bm25", "semantic_vector"]},
            "rerank": {"matched_terms": ["project", "capex"], "provenance_score": 1.0},
            "field_sources": {"amount": {"block_id": "blk1"}},
        },
    )

    citation = _citations([hit])[0]
    payload = _question_payload("Project Alpha CAPEX", [citation])

    assert citation.block_type == "agent_chunk"
    assert citation.match_source == "hybrid_rrf"
    assert citation.metadata["fusion"]["method"] == "rrf"
    trace = payload["citations"][0]["retrieval_trace"]
    assert trace["fusion"]["sources"] == ["bm25", "semantic_vector"]
    assert trace["rerank"]["matched_terms"] == ["project", "capex"]
    assert trace["has_field_sources"] is True
