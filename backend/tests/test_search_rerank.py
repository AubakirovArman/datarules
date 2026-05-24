from datarules_api.schemas import SearchHit
from datarules_api.search_rerank import rerank_hits


def test_rerank_prefers_term_match_with_provenance() -> None:
    weak = _hit("weak", "Generic document text", "raw_block", {}, 0.3)
    strong = _hit(
        "strong",
        "Project Alpha CAPEX 1200 USD",
        "hybrid_rrf",
        {"field_sources": {"amount": {"block_id": "blk2"}}, "source_confidence": 0.95},
        0.2,
    )

    rows = rerank_hits("Project Alpha CAPEX", [weak, strong], 2)

    assert rows[0].document_id == "strong"
    assert rows[0].metadata["rerank"]["method"] == "deterministic_v1"
    assert rows[0].metadata["rerank"]["matched_terms"] == ["project", "alpha", "capex"]
    assert rows[0].metadata["rerank"]["provenance_score"] == 1.0
    assert rows[0].score > rows[1].score


def _hit(document_id: str, text: str, source: str, metadata: dict, score: float) -> SearchHit:
    return SearchHit(
        document_id=document_id,
        block_id=f"blk_{document_id}",
        file_name=f"{document_id}.txt",
        block_type="agent_chunk" if source != "raw_block" else "paragraph",
        page=1,
        sheet_name=None,
        slide_number=None,
        text=text,
        score=score,
        match_source=source,
        target_table="projects" if source != "raw_block" else None,
        metadata=metadata,
    )
