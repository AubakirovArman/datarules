from .schemas import SearchHit

RRF_K = 60
SOURCE_PRIORITY = {
    "bm25": 5,
    "semantic_vector": 4,
    "fts_keyword": 3,
    "raw_block": 2,
}


def rrf_fuse_hits(hits: list[SearchHit], limit: int, embedding_status: str | None = None) -> list[SearchHit]:
    grouped: dict[tuple[str, str, str], list[tuple[int, SearchHit]]] = {}
    source_counts: dict[str, int] = {}
    for rank, hit in enumerate(hits, start=1):
        key = (hit.document_id, hit.block_id, hit.target_table or "")
        grouped.setdefault(key, []).append((rank, hit))
        source = hit.match_source or hit.block_type
        source_counts[source] = source_counts.get(source, 0) + 1
    fused = [_fused_hit(rows, source_counts, embedding_status) for rows in grouped.values()]
    return sorted(fused, key=lambda item: item.score, reverse=True)[:limit]


def _fused_hit(
    rows: list[tuple[int, SearchHit]],
    source_counts: dict[str, int],
    embedding_status: str | None,
) -> SearchHit:
    best = _best_hit(rows)
    sources = [_source_name(hit) for _, hit in rows]
    rrf = sum(1.0 / (RRF_K + rank) for rank, _ in rows)
    score = rrf + max(_source_bonus(source) for source in sources) + min(float(best.score or 0.0), 2.0) / 100
    metadata = {
        **(best.metadata or {}),
        "fusion": {
            "method": "rrf",
            "sources": sorted(set(sources)),
            "source_ranks": {source: _rank_for_source(rows, source) for source in sorted(set(sources))},
            "rrf_score": round(rrf, 6),
            "source_counts": source_counts,
        },
    }
    if embedding_status:
        metadata["embedding_status"] = embedding_status
    return best.model_copy(update={"score": round(score, 6), "match_source": _match_source(sources), "metadata": metadata})


def _best_hit(rows: list[tuple[int, SearchHit]]) -> SearchHit:
    return sorted(rows, key=lambda item: (_source_bonus(_source_name(item[1])), item[1].score), reverse=True)[0][1]


def _source_name(hit: SearchHit) -> str:
    return str(hit.match_source or hit.block_type)


def _source_bonus(source: str) -> float:
    return SOURCE_PRIORITY.get(source, 1) / 1000


def _rank_for_source(rows: list[tuple[int, SearchHit]], source: str) -> int:
    ranks = [rank for rank, hit in rows if _source_name(hit) == source]
    return min(ranks) if ranks else 0


def _match_source(sources: list[str]) -> str:
    if len(set(sources)) > 1:
        return "hybrid_rrf"
    return sources[0]
