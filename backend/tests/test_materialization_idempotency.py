from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.db import SessionLocal
from datarules_api.main import app
from helpers import confirm_all_reviews


def test_repeated_load_plans_do_not_duplicate_agent_chunks() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Idempotent load", "description": "No duplicate chunks"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("stable.txt", b"Stable Project\nCAPEX 400 USD", "text/plain")},
        )
        document_id = upload.json()[0]["id"]
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "stable_agent_chunks")

        first = _create_and_confirm(client, dataset["id"], "stable_agent_chunks")
        second = _create_and_confirm(client, dataset["id"], "stable_agent_chunks")
        chunk_table = second["agent_preparation_json"]["chunk_table"]

        assert first["agent_preparation_json"]["inserted_chunks"] == 1
        assert second["agent_preparation_json"]["inserted_chunks"] == 1
        assert second["agent_preparation_json"]["verification"]["chunk_table"]["rows_for_plan"] == 1
        assert _count("stable_agent_chunks", document_id) == 1
        assert _count(chunk_table, document_id) == 1


def _create_and_confirm(client: TestClient, dataset_id: str, table: str) -> dict:
    plan = client.post(
        f"/datasets/{dataset_id}/load-plans",
        json={"target_mode": "new", "target_table": table},
    ).json()
    response = client.post(f"/load-plans/{plan['id']}/confirm")
    assert response.status_code == 200
    return response.json()


def _count(table: str, document_id: str) -> int:
    with SessionLocal() as db:
        return int(
            db.execute(
                text(f'SELECT count(*) FROM public."{table}" WHERE source_document_id = :document_id'),
                {"document_id": document_id},
            ).scalar()
            or 0
        )


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
