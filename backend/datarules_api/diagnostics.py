from pathlib import Path
from time import perf_counter
from typing import Any
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from .config import get_settings
from .db import SessionLocal, engine
from .embeddings import embed_texts
from .ingestion_state import ACTIVE_STATUSES
from .models import IngestionJob
from .parsers.common import clean_text
from .secret_store import secret_key_status

router = APIRouter()
REQUIRED_EXTENSIONS = {"vector", "pg_search", "pg_trgm"}


@router.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    checks = [_database_check(), _storage_check(), _ingestion_runner_check(), _gemma_check(), _embedding_check(), _secret_check()]
    return {
        "status": _overall_status(checks),
        "checks": checks,
        "runtime": _runtime_summary(),
    }


def _database_check() -> dict[str, Any]:
    started = perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            extensions = {
                row[0]
                for row in conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_search', 'pg_trgm')")
                )
            }
        missing = sorted(REQUIRED_EXTENSIONS - extensions)
        status = "ok" if not missing else "warning"
        return _check("database", status, _elapsed(started), {"extensions": sorted(extensions), "missing": missing})
    except Exception as exc:
        return _check("database", "failed", _elapsed(started), {"error": clean_text(str(exc))[:300]})


def _storage_check() -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    paths = [settings.raw_storage_dir, settings.canonical_storage_dir, settings.page_image_dir]
    try:
        for path in paths:
            _write_probe(path)
        return _check("storage", "ok", _elapsed(started), {"paths": [str(path) for path in paths]})
    except Exception as exc:
        return _check("storage", "failed", _elapsed(started), {"error": clean_text(str(exc))[:300]})


def _gemma_check() -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    if not settings.enable_gemma_calls:
        return _check("gemma", "disabled", _elapsed(started), {"model": settings.gemma_model_id, "gpu_id": settings.gemma_gpu_id})
    if not settings.gemma_base_url:
        return _check("gemma", "failed", _elapsed(started), {"error": "GEMMA_BASE_URL is empty."})
    url = settings.gemma_base_url.rstrip("/") + "/models"
    try:
        with httpx.Client(timeout=min(8, settings.gemma_timeout_seconds)) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {settings.gemma_api_key}"})
            response.raise_for_status()
        return _check("gemma", "ok", _elapsed(started), {"model": settings.gemma_model_id, "url": url, "gpu_id": settings.gemma_gpu_id})
    except httpx.HTTPError as exc:
        return _check("gemma", "failed", _elapsed(started), {"model": settings.gemma_model_id, "url": url, "error": str(exc)[:300]})


def _embedding_check() -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    if not settings.enable_embedding_calls:
        return _check("embeddings", "disabled", _elapsed(started), {"model": settings.embedding_model_id})
    vectors, status = embed_texts(["DataRules diagnostic probe"])
    level = "ok" if status == "ready" and vectors else "failed"
    return _check(
        "embeddings",
        level,
        _elapsed(started),
        {"model": settings.embedding_model_id, "status": status, "dimensions": len(vectors[0]) if vectors else 0},
    )


def _ingestion_runner_check() -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    cutoff = datetime.utcnow() - timedelta(seconds=settings.ingestion_stale_seconds)
    with SessionLocal() as db:
        active = db.query(IngestionJob).filter(IngestionJob.status.in_(ACTIVE_STATUSES)).all()
    stale = [job for job in active if (job.heartbeat_at or job.updated_at or job.created_at) < cutoff]
    counts = {status: sum(1 for job in active if job.status == status) for status in ACTIVE_STATUSES}
    return _check(
        "ingestion_runner",
        "warning" if stale else "ok",
        _elapsed(started),
        {
            "active": len(active),
            "stale": len(stale),
            "counts": counts,
            "stale_seconds": settings.ingestion_stale_seconds,
            "max_attempts": settings.ingestion_max_attempts,
            "stale_jobs": [{"id": job.id, "stage": job.current_stage, "attempt": job.attempt_count} for job in stale[:8]],
        },
    )


def _secret_check() -> dict[str, Any]:
    status = secret_key_status()
    return _check("secret_storage", "ok" if status == "configured" else "warning", 0, {"status": status})


def _runtime_summary() -> dict[str, Any]:
    settings = get_settings()
    return {
        "gemma_base_url": settings.gemma_base_url,
        "gemma_gpu_id": settings.gemma_gpu_id,
        "embedding_base_url": settings.embedding_base_url,
        "database_url_host": "127.0.0.1:55433",
        "ingestion_stale_seconds": settings.ingestion_stale_seconds,
        "ingestion_max_attempts": settings.ingestion_max_attempts,
        "secret_storage": secret_key_status(),
    }


def _write_probe(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".datarules_write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


def _check(key: str, status: str, latency_ms: int, details: dict[str, Any]) -> dict[str, Any]:
    return {"key": key, "status": status, "latency_ms": latency_ms, "details": details}


def _elapsed(started: float) -> int:
    return round((perf_counter() - started) * 1000)


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "failed" for check in checks):
        return "failed"
    if any(check["status"] in {"warning", "disabled"} for check in checks):
        return "attention"
    return "ok"
