from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.db import SessionLocal
from datarules_api.main import app
from helpers import confirm_all_reviews


def test_analysis_only_indexes_agent_chunks_without_business_table() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Analysis only", "description": "Index"}).json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("analysis.txt", b"Analysis Project\nCAPEX 1200 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "analysis_only")

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "analysis_only", "target_table": "analysis_only"},
        ).json()
        assert plan["status"] == "needs_confirmation"

        loaded = client.post(f"/load-plans/{plan['id']}/confirm").json()
        agent = loaded["agent_preparation_json"]
        assert loaded["status"] == "loaded"
        assert agent["stage"] == "indexed"
        assert agent["analysis_only"] is True
        assert agent["inserted_records"] == 0
        assert agent["inserted_chunks"] > 0
        assert _table_exists("analysis_only") is False
        assert _table_exists(agent["chunk_table"]) is True
        assert _row_count(agent["chunk_table"]) == agent["inserted_chunks"]

        report = client.get(f"/load-plans/{plan['id']}/report").json()
        assert report["live_verification"]["status"] == "ready"
        assert report["live_verification"]["target_table"]["required"] is False
        hits = client.post(f"/datasets/{dataset_id}/search", json={"query": "CAPEX", "limit": 5}).json()
        assert any(hit["target_table"] == "analysis_only" for hit in hits)
        reindexed = client.post(f"/load-plans/{plan['id']}/reindex").json()
        assert reindexed["agent_preparation_json"]["stage"] == "indexed"
        assert reindexed["agent_preparation_json"]["inserted_chunks"] == agent["inserted_chunks"]
        assert client.get(f"/load-plans/{plan['id']}/rows").status_code == 400
        exported = client.get(f"/load-plans/{plan['id']}/export.json").json()
        assert exported["rows"][0]["source_file"] == "analysis.txt"


def _table_exists(table: str) -> bool:
    with SessionLocal() as db:
        value = db.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}).scalar()
        return value is not None


def _row_count(table: str) -> int:
    with SessionLocal() as db:
        return int(db.execute(text(f'SELECT count(*) FROM public."{table}"')).scalar() or 0)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
