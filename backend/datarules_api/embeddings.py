from typing import Any

import httpx

from .config import get_settings


def embed_texts(texts: list[str]) -> tuple[list[list[float]], str]:
    settings = get_settings()
    if not texts:
        return [], "empty"
    if not settings.enable_embedding_calls or not settings.embedding_base_url:
        return [], "disabled"
    payload = {
        "texts": texts,
        "return_dense": True,
        "return_sparse": False,
        "return_colbert_vecs": False,
    }
    try:
        url = settings.embedding_base_url.rstrip("/") + "/encode"
        with httpx.Client(timeout=settings.embedding_timeout_seconds) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            vectors = _vectors(response.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return [], "failed"
    if not vectors:
        return [], "empty_response"
    return [_trim(vector, settings.embedding_dimensions) for vector in vectors], "ready"


def vector_literal(vector: list[float] | None) -> str | None:
    if not vector:
        return None
    return "[" + ",".join(f"{float(value):.8f}" for value in vector) + "]"


def _vectors(value: dict[str, Any]) -> list[list[float]]:
    if isinstance(value.get("dense_vecs"), list):
        return value["dense_vecs"]
    data = value.get("data")
    if isinstance(data, list):
        return [item["embedding"] for item in data if isinstance(item, dict) and "embedding" in item]
    embeddings = value.get("embeddings")
    return embeddings if isinstance(embeddings, list) else []


def _trim(vector: list[Any], dimensions: int) -> list[float]:
    values = [float(item) for item in vector[:dimensions]]
    if len(values) < dimensions:
        values.extend([0.0] * (dimensions - len(values)))
    return values
