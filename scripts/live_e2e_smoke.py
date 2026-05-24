#!/usr/bin/env python3
import os
import sys
import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import create_engine, text

from datarules_api.config import get_settings
from datarules_api.db import SessionLocal
from datarules_api.models import (
    AgentAnswer,
    AuditEvent,
    Dataset,
    Document,
    DocumentAiSummary,
    DocumentBlock,
    DocumentExtractionRun,
    DocumentReview,
    GoldenCheck,
    GoldenEvaluationRun,
    IngestionJob,
    JobEvent,
    LoadPlan,
    LoadPlanEvent,
    SchemaProposal,
    SchemaVersion,
    TableCatalog,
)


API_URL = os.environ.get("DATARULES_API_URL", "http://127.0.0.1:8017").rstrip("/")
TIMEOUT = float(os.environ.get("DATARULES_SMOKE_TIMEOUT", "180"))
KEEP_DATA = os.environ.get("DATARULES_SMOKE_KEEP_DATA", "").lower() in {"1", "true", "yes"}


def main() -> int:
    suffix = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    table = f"e2e_smoke_{suffix}"
    dataset_id = ""
    try:
        client = httpx.Client(base_url=API_URL, timeout=httpx.Timeout(TIMEOUT, connect=10))
        _stage("health", _get(client, "/health"))
        diagnostics = _get(client, "/diagnostics")
        _require(diagnostics.get("status") == "ok", f"diagnostics not ok: {diagnostics}")
        _require("ingestion_runner" in {row["key"] for row in diagnostics["checks"]}, f"runner diagnostics missing: {diagnostics}")
        _stage("diagnostics", {"status": diagnostics["status"], "checks": [row["key"] for row in diagnostics["checks"]]})
        dataset_id = _create_dataset(client, suffix)
        document_ids = _upload_documents(client, dataset_id)
        job = _post(client, f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, str(job["id"]))
        _assert_summaries(client, dataset_id, len(document_ids))
        _confirm_reviews(client, dataset_id, table)
        _assert_schema_chat(client, dataset_id)
        plan = _create_load_plan(client, dataset_id, table, document_ids)
        loaded = _post(client, f"/load-plans/{plan['id']}/confirm")
        _require(loaded["status"] == "loaded", f"load failed: {loaded}")
        _assert_readiness(client, dataset_id)
        _assert_search_and_answer(client, dataset_id)
        _assert_golden_run(client, dataset_id)
        _assert_golden_gate(client, dataset_id)
        _stage("complete", {"dataset_id": dataset_id, "table": table})
        return 0
    except Exception as exc:
        print(f"[live-e2e] failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if dataset_id and not KEEP_DATA:
            _cleanup(dataset_id, table)


def _create_dataset(client: httpx.Client, suffix: str) -> str:
    payload = {"name": f"Live E2E {suffix}", "description": "Temporary DataRules live smoke dataset"}
    dataset = _post(client, "/datasets", payload)
    _stage("dataset", {"id": dataset["id"]})
    return str(dataset["id"])


def _upload_documents(client: httpx.Client, dataset_id: str) -> list[str]:
    files = [
        ("files", ("alpha.txt", b"Project Alpha\nCAPEX 1200 USD\nYear 2026", "text/plain")),
        ("files", ("beta.csv", b"name,amount,currency,year\nProject Beta,3400,USD,2027\n", "text/csv")),
    ]
    uploaded = _post_files(client, f"/datasets/{dataset_id}/files", files)
    ids = [str(row["id"]) for row in uploaded]
    _require(len(ids) == 2, f"expected two uploaded docs, got {uploaded}")
    _stage("upload", {"documents": ids})
    return ids


def _wait_job(client: httpx.Client, job_id: str) -> None:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        job = _get(client, f"/jobs/{job_id}")
        if job["status"] in {"waiting_review", "completed"}:
            _require(job["attempt_count"] >= 1 and job["heartbeat_at"], f"job runtime metadata missing: {job}")
            _stage("ingestion", {
                "job_id": job_id,
                "status": job["status"],
                "stage": job["current_stage"],
                "attempt": f"{job['attempt_count']}/{job['max_attempts']}",
            })
            return
        if job["status"] in {"failed", "cancelled"}:
            raise RuntimeError(f"ingestion stopped: {job}")
        time.sleep(1)
    raise TimeoutError(f"job {job_id} did not finish in {TIMEOUT}s")


def _assert_summaries(client: httpx.Client, dataset_id: str, count: int) -> None:
    summaries = _get(client, f"/datasets/{dataset_id}/document-summaries?language=ru")
    _require(len(summaries) == count, f"missing summaries: {summaries}")
    _require(all(row["summary"] and row["blocks"] for row in summaries), f"weak summaries: {summaries}")
    _stage("summaries", {"documents": len(summaries), "sources": [row["summary_source"] for row in summaries]})


def _confirm_reviews(client: httpx.Client, dataset_id: str, table: str) -> None:
    reviews = _get(client, f"/datasets/{dataset_id}/document-reviews")
    _require(reviews, "reviews were not created")
    for review in reviews:
        option = review["doc_type_options"][0]
        _post(client, f"/document-reviews/{review['id']}/decision", {
            "selected_doc_type": option["value"],
            "selected_table": table,
            "notes": "Live E2E route confirmation",
        })
    confirmed = _get(client, f"/datasets/{dataset_id}/document-reviews")
    _require(all(row["status"] == "confirmed" for row in confirmed), f"unconfirmed reviews: {confirmed}")
    _stage("routing", {"confirmed": len(confirmed), "table": table})


def _assert_schema_chat(client: httpx.Client, dataset_id: str) -> None:
    chat = _post(client, f"/datasets/{dataset_id}/schema-chat", {
        "language": "ru",
        "message": "Нужна новая таблица проектов с суммой, валютой, годом и ссылками на источник",
    })
    usage = chat["proposal_json"].get("context_usage", {})
    _require(usage.get("document_summaries", 0) >= 1, f"schema chat ignored summaries: {chat}")
    _stage("schema_chat", {"source": chat["proposal_json"].get("source"), "usage": usage})


def _create_load_plan(client: httpx.Client, dataset_id: str, table: str, document_ids: list[str]) -> dict[str, Any]:
    schema = {
        "description": "Live E2E smoke project table",
        "schema_source": "user_supplied_schema",
        "target_columns": [
            {"name": "title", "type": "text", "required": False},
            {"name": "amount", "type": "text", "required": False},
            {"name": "currency", "type": "text", "required": False},
            {"name": "year", "type": "text", "required": False},
        ],
        "source_references_required": True,
    }
    plan = _post(client, f"/datasets/{dataset_id}/load-plans", {
        "target_mode": "new",
        "target_table": table,
        "schema_json": schema,
        "document_ids": document_ids,
    })
    _require(plan["status"] == "needs_confirmation", f"plan blocked: {plan}")
    _require(plan["preview_rows"], f"empty preview: {plan}")
    _stage("preview", {"plan_id": plan["id"], "rows": len(plan["preview_rows"])})
    return plan


def _assert_readiness(client: httpx.Client, dataset_id: str) -> None:
    readiness = _get(client, f"/datasets/{dataset_id}/readiness")
    _require(readiness["status"] == "ready_for_agent", f"not ready: {readiness}")
    _require(readiness["agent"]["ready"] is True, f"agent not ready: {readiness}")
    _stage("readiness", {"score": readiness["score"], "agent_tables": readiness["agent"]["loaded_plans"]})


def _assert_search_and_answer(client: httpx.Client, dataset_id: str) -> None:
    hits = _post(client, f"/datasets/{dataset_id}/search", {"query": "Project Alpha CAPEX", "limit": 8})
    _require(any(hit["block_type"] == "agent_chunk" for hit in hits), f"agent search missing: {hits}")
    answer = _post(client, f"/datasets/{dataset_id}/ask", {"query": "What is Project Alpha CAPEX?", "limit": 8})
    _require(answer.get("answer_id"), f"answer was not persisted: {answer}")
    _require(answer.get("citations"), f"answer has no citations: {answer}")
    _stage("search_ask", {"hits": len(hits), "confidence": answer["confidence"], "source": answer["model_source"]})


def _assert_golden_run(client: httpx.Client, dataset_id: str) -> None:
    _post(client, f"/datasets/{dataset_id}/golden-checks", {
        "question": "What is Project Alpha CAPEX?",
        "expected_terms": ["Project Alpha", "1200", "USD"],
    })
    run = _post(client, f"/datasets/{dataset_id}/golden-checks/run")
    _require(run["total"] == 1, f"golden run missing check: {run}")
    _require(run["snapshot"]["ready_agent_tables"] >= 1, f"golden snapshot not linked to agent state: {run}")
    _stage("golden", {"score": run["score"], "status": run["status"], "snapshot": run["snapshot"]["answer_prompt_version"]})


def _assert_golden_gate(client: httpx.Client, dataset_id: str) -> None:
    gate = _get(client, f"/datasets/{dataset_id}/golden-gate")
    _require(gate["status"] == "passed", f"golden gate failed: {gate}")
    _require(gate["latest_run"]["snapshot"]["ready_agent_tables"] >= 1, f"golden gate snapshot missing agent table: {gate}")
    _stage("golden_gate", {"status": gate["status"], "thresholds": gate["thresholds"]})


def _get(client: httpx.Client, path: str) -> Any:
    response = client.get(path)
    return _json(response)


def _post(client: httpx.Client, path: str, payload: dict[str, Any] | None = None) -> Any:
    response = client.post(path, json=payload or {})
    return _json(response)


def _post_files(client: httpx.Client, path: str, files: list[tuple[str, tuple[str, bytes, str]]]) -> Any:
    response = client.post(path, files=files)
    return _json(response)


def _json(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        raise RuntimeError(f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text[:1200]}")
    return response.json()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _stage(name: str, payload: dict[str, Any]) -> None:
    print(f"[live-e2e] {name}: {payload}")


def _cleanup(dataset_id: str, table: str) -> None:
    try:
        with SessionLocal() as db:
            plans = db.query(LoadPlan).filter(LoadPlan.dataset_id == dataset_id).all()
            chunk_tables = [str((plan.agent_preparation_json or {}).get("chunk_table") or "") for plan in plans]
            _drop_tables([table, *chunk_tables])
            _delete_db_rows(db, dataset_id, [plan.id for plan in plans], table)
            db.commit()
        _stage("cleanup", {"dataset_id": dataset_id, "table": table})
    except Exception as exc:
        print(f"[live-e2e] cleanup warning: {exc}", file=sys.stderr)


def _drop_tables(tables: list[str]) -> None:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
    with engine.begin() as conn:
        for table in sorted({item for item in tables if item.startswith("e2e_smoke_")}):
            conn.execute(text(f'DROP TABLE IF EXISTS public."{table.replace(chr(34), chr(34) + chr(34))}" CASCADE'))


def _delete_db_rows(db: Any, dataset_id: str, plan_ids: list[str], table: str) -> None:
    job_ids = [row[0] for row in db.query(IngestionJob.id).filter(IngestionJob.dataset_id == dataset_id).all()]
    doc_ids = [row[0] for row in db.query(Document.id).filter(Document.dataset_id == dataset_id).all()]
    if job_ids:
        db.query(JobEvent).filter(JobEvent.job_id.in_(job_ids)).delete(synchronize_session=False)
    if plan_ids:
        db.query(LoadPlanEvent).filter(LoadPlanEvent.load_plan_id.in_(plan_ids)).delete(synchronize_session=False)
    if doc_ids:
        db.query(DocumentBlock).filter(DocumentBlock.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(DocumentExtractionRun).filter(DocumentExtractionRun.document_id.in_(doc_ids)).delete(synchronize_session=False)
    for model in (AgentAnswer, GoldenEvaluationRun, GoldenCheck, LoadPlan, SchemaVersion, SchemaProposal, DocumentReview, IngestionJob, Document):
        db.query(model).filter(model.dataset_id == dataset_id).delete(synchronize_session=False)
    db.query(TableCatalog).filter(TableCatalog.table_name == table).delete(synchronize_session=False)
    db.query(AuditEvent).filter(AuditEvent.dataset_id == dataset_id).delete(synchronize_session=False)
    db.query(Dataset).filter(Dataset.id == dataset_id).delete(synchronize_session=False)


if __name__ == "__main__":
    raise SystemExit(main())
