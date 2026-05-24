from pathlib import Path

from datarules_api.config import Settings
from datarules_api.llm.gemma import GemmaClient
from datarules_api.parsers.registry import parse_document
from datarules_api.parsers.common import CanonicalBlock
from datarules_api.vision_extraction import enrich_image_pages


def test_text_parser_returns_canonical_blocks(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("Project Alpha\n\nCAPEX 1200000 USD", encoding="utf-8")

    result = parse_document(path, "text/plain", tmp_path / "images")

    assert result.file_type == "text"
    assert len(result.blocks) == 2
    assert result.blocks[0].text == "Project Alpha"


def test_csv_parser_keeps_table_rows(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("project,amount\nSolar,1200\n", encoding="utf-8")

    result = parse_document(path, "text/csv", tmp_path / "images")

    assert result.blocks[0].block_type == "table"
    assert result.blocks[0].table_json["rows"][1] == ["Solar", "1200"]


def test_fallback_schema_requires_source_references() -> None:
    settings = Settings(enable_gemma_calls=False, gemma_base_url=None)
    proposal = GemmaClient(settings).propose_schema_sync(
        [{"file_name": "a.txt", "block_type": "paragraph", "text": "CAPEX 1M USD"}]
    )
    columns = proposal["tables"][0]["columns"]
    names = {column["name"] for column in columns}

    assert "source_document_id" in names
    assert "source_block_id" in names


def test_image_page_enrichment_creates_text_and_table_blocks() -> None:
    block = CanonicalBlock(
        block_type="image_page",
        page=2,
        confidence=0.4,
        metadata={"image_path": "/tmp/page.png", "requires_multimodal_ocr": True},
    )

    def fake_extractor(_: str, page: int | None) -> dict:
        return {
            "source": "test_vision",
            "page_summary": f"Page {page} contains Project Alpha.",
            "blocks": [{"type": "paragraph", "text": "Project Alpha CAPEX 1200 USD", "confidence": 0.91}],
            "tables": [{"rows": [["Project", "Amount"], ["Alpha", "1200"]], "confidence": 0.88}],
            "quality_notes": ["synthetic"],
        }

    enriched = enrich_image_pages([block], extractor=fake_extractor)

    assert [item.block_type for item in enriched] == ["image_page", "paragraph", "paragraph", "table"]
    assert enriched[1].page == 2
    assert enriched[2].metadata["source"] == "gemma4_vision"
    assert enriched[3].table_json["rows"][1] == ["Alpha", "1200"]
