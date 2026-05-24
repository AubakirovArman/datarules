from datarules_api.answer_grounding import guard_answer, guarded_confidence
from datarules_api.schemas import AskCitation


def test_grounding_guard_adds_missing_citation_markers() -> None:
    answer, source, grounding = guard_answer("Что такое Project Alpha?", "Project Alpha имеет CAPEX.", [_citation("[1]")], "gemma4")

    assert "Источники: [1]" in answer
    assert source == "gemma4_grounding_guard"
    assert grounding["status"] == "markers_added"
    assert grounding["valid_markers"] == ["[1]"]
    assert guarded_confidence("high", grounding) == "medium"


def test_grounding_guard_preserves_grounded_answer() -> None:
    answer, source, grounding = guard_answer("What is Project Alpha?", "Project Alpha has CAPEX [1].", [_citation("[1]")], "gemma4")

    assert answer == "Project Alpha has CAPEX [1]."
    assert source == "gemma4"
    assert grounding["status"] == "grounded"
    assert guarded_confidence("medium", grounding) == "medium"


def test_grounding_coverage_is_capped() -> None:
    citations = [_citation("[1]"), _citation("[2]"), _citation("[3]")]
    _, _, grounding = guard_answer("Q", "Answer [1] [2] [3]", citations, "gemma4")

    assert grounding["coverage"] == 1.0


def _citation(marker: str) -> AskCitation:
    return AskCitation(
        marker=marker,
        document_id="doc1",
        block_id="blk1",
        file_name="source.txt",
        page=1,
        sheet_name=None,
        target_table="projects",
        text="Project Alpha CAPEX 1200 USD",
        score=0.9,
    )
