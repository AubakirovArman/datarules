from pathlib import Path
from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import Document
from helpers import confirm_all_reviews


def test_repair_document_reextracts_and_invalidates_loaded_plan() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Repair", "description": "Re-extract one doc"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("repair.txt", b"Old Repair Project\nCAPEX 100 USD", "text/plain")},
        ).json()
        document_id = upload[0]["id"]
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        initial_runs = client.get(f"/datasets/{dataset['id']}/files/{document_id}/extraction-runs").json()["runs"]
        assert initial_runs[0]["run_type"] == "ingestion"
        assert initial_runs[0]["metrics"]["blocks"] >= 1
        initial_run_id = initial_runs[0]["id"]
        confirm_all_reviews(client, dataset["id"], "repair_projects")

        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "repair_projects"},
        ).json()
        loaded = client.post(f"/load-plans/{plan['id']}/confirm").json()
        chunk_table = loaded["agent_preparation_json"]["chunk_table"]
        assert _count("repair_projects", document_id) == 1
        assert _count(chunk_table, document_id) == 1

        _rewrite_raw_file(document_id, b"New Repair Project\nCAPEX 777 USD")
        repaired = client.post(f"/datasets/{dataset['id']}/files/{document_id}/repair-extraction")
        assert repaired.status_code == 200
        body = repaired.json()
        assert body["status"] == "repaired"
        assert body["materialized_cleanup"]["target_rows"] == 1
        assert _count("repair_projects", document_id) == 0
        assert _count(chunk_table, document_id) == 0

        summaries = client.get(f"/datasets/{dataset['id']}/document-summaries").json()
        assert "New Repair Project" in summaries[0]["summary"] or "New Repair Project" in str(summaries[0]["ai_summary"])
        preview_diff = client.get(f"/load-plans/{plan['id']}/preview-diff")
        assert preview_diff.status_code == 200
        assert preview_diff.json()["summary"]["changed_rows"] >= 1
        assert preview_diff.json()["changed_rows"][0]["source_changed"] is True
        repaired_runs = client.get(f"/datasets/{dataset['id']}/files/{document_id}/extraction-runs").json()["runs"]
        assert [run["run_type"] for run in repaired_runs[:2]] == ["repair", "ingestion"]
        diff = client.get(f"/datasets/{dataset['id']}/files/{document_id}/extraction-runs/{initial_run_id}/diff").json()
        assert diff["summary"]["changed_blocks"] >= 1
        assert "Old Repair Project" in str(diff["changed_blocks"])
        assert "New Repair Project" in str(diff["changed_blocks"])
        plans = client.get(f"/datasets/{dataset['id']}/load-plans").json()
        stale = next(item for item in plans if item["id"] == plan["id"])
        assert stale["status"] == "blocked"
        assert stale["events"][-1]["action"] == "source_repaired"
        assert any(issue["code"] == "source_repaired" for issue in stale["validation_issues"])

        rollback = client.post(f"/datasets/{dataset['id']}/files/{document_id}/extraction-runs/{initial_run_id}/rollback")
        assert rollback.status_code == 200
        assert rollback.json()["new_run"]["run_type"] == "rollback"
        canonical = client.get(f"/datasets/{dataset['id']}/files/{document_id}/canonical").json()
        assert "Old Repair Project" in str(canonical)
        runs = client.get(f"/datasets/{dataset['id']}/files/{document_id}/extraction-runs").json()["runs"]
        assert runs[0]["run_type"] == "rollback"


def _rewrite_raw_file(document_id: str, content: bytes) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document
        Path(document.storage_path).write_bytes(content)


def _count(table: str, document_id: str) -> int:
    with SessionLocal() as db:
        return int(db.execute(text(f'SELECT count(*) FROM public."{table}" WHERE source_document_id = :document_id'), {"document_id": document_id}).scalar() or 0)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed", "cancelled"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
