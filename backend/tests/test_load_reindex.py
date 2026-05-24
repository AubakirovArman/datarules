from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.db import SessionLocal
from datarules_api.main import app
from helpers import confirm_all_reviews


def test_reindex_loaded_plan_restores_agent_chunks() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Reindex", "description": "Agent backfill"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("reindex.txt", b"Reindex Project\nCAPEX 610 USD", "text/plain")},
        )
        document_id = upload.json()[0]["id"]
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "reindex_projects")

        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "reindex_projects"},
        ).json()
        loaded = client.post(f"/load-plans/{plan['id']}/confirm").json()
        chunk_table = loaded["agent_preparation_json"]["chunk_table"]
        _delete_chunks(chunk_table, document_id)
        assert _count(chunk_table, document_id) == 0

        response = client.post(f"/load-plans/{plan['id']}/reindex")
        assert response.status_code == 200
        body = response.json()
        agent = body["agent_preparation_json"]
        assert body["status"] == "loaded"
        assert body["events"][-1]["action"] == "agent_reindexed"
        assert agent["last_action"] == "reindexed"
        assert agent["verification"]["chunk_table"]["rows_for_plan"] == 1
        assert _count(chunk_table, document_id) == 1


def _delete_chunks(table: str, document_id: str) -> None:
    with SessionLocal() as db:
        db.execute(text(f'DELETE FROM public."{table}" WHERE source_document_id = :document_id'), {"document_id": document_id})
        db.commit()


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
