from datarules_api.schemas import SearchHit
from datarules_api.search_fusion import rrf_fuse_hits


def test_rrf_fusion_combines_sources_and_explains_ranks() -> None:
    hits = [
        _hit("doc1", "blk1", "bm25", 1.4),
        _hit("doc2", "blk2", "bm25", 1.3),
        _hit("doc1", "blk1", "semantic_vector", 1.1),
        _hit("doc3", "blk3", "raw_block", 0.35),
    ]

    fused = rrf_fuse_hits(hits, 3, embedding_status="ready")

    assert fused[0].document_id == "doc1"
    assert fused[0].match_source == "hybrid_rrf"
    assert fused[0].metadata["embedding_status"] == "ready"
    assert fused[0].metadata["fusion"]["method"] == "rrf"
    assert fused[0].metadata["fusion"]["sources"] == ["bm25", "semantic_vector"]
    assert fused[0].metadata["fusion"]["source_ranks"] == {"bm25": 1, "semantic_vector": 3}
    assert len(fused) == 3


def _hit(document_id: str, block_id: str, source: str, score: float) -> SearchHit:
    return SearchHit(
        document_id=document_id,
        block_id=block_id,
        file_name=f"{document_id}.txt",
        block_type="agent_chunk" if source != "raw_block" else "paragraph",
        page=1,
        sheet_name=None,
        slide_number=None,
        text=f"{document_id} {block_id}",
        score=score,
        match_source=source,
        target_table="projects" if source != "raw_block" else None,
        metadata={"field_sources": {"title": {"block_id": block_id}}},
    )
