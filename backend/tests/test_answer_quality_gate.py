from datarules_api.answer_quality import answer_quality_gate, combined_quality_gate, insufficient_answer, retrieval_quality_gate
from datarules_api.schemas import AskCitation


def test_retrieval_quality_gate_blocks_weak_unmatched_sources() -> None:
    gate = retrieval_quality_gate("Найди неизвестный CAPEX", [_citation(score=0.01, matched=[])])

    assert gate["status"] == "blocked"
    assert "retrieval_score_too_low" in gate["reasons"]
    assert "no_query_terms_matched" in gate["reasons"]


def test_retrieval_quality_gate_allows_low_score_with_term_match() -> None:
    gate = retrieval_quality_gate("CAPEX проекты", [_citation(score=0.19, matched=["capex"])])

    assert gate["status"] == "warning"
    assert "low_retrieval_score" in gate["reasons"]
    assert gate["metrics"]["term_coverage"] > 0


def test_answer_quality_gate_blocks_invalid_markers() -> None:
    gate = answer_quality_gate({"invalid_markers": ["[9]"], "valid_markers": [], "coverage": 0})
    combined = combined_quality_gate(retrieval_quality_gate("CAPEX", [_citation()]), gate)

    assert combined["status"] == "blocked"
    assert "invalid_citation_markers" in combined["reasons"]
    assert "Недостаточно подтверждённых источников" in insufficient_answer("Что про CAPEX?", combined)


def _citation(score: float = 0.9, matched: list[str] | None = None) -> AskCitation:
    return AskCitation(
        marker="[1]",
        document_id="doc1",
        block_id="blk1",
        file_name="source.txt",
        block_type="agent_chunk",
        page=1,
        sheet_name=None,
        target_table="projects",
        text="Project Alpha CAPEX 1200 USD",
        score=score,
        match_source="raw_block",
        metadata={"rerank": {"matched_terms": matched if matched is not None else ["capex"]}},
    )
