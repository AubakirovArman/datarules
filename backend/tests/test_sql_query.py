from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_sql_query_reads_loaded_table_safely() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "SQL", "description": "Read only"}).json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("sql.txt", b"SQL Project\nCAPEX 750 USD\nYear 2026", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "sql_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "sql_projects"},
        ).json()
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 200

        result = client.post(
            f"/datasets/{dataset_id}/sql-query",
            json={"plan_id": plan["id"], "sql": "select id, content, source_file from sql_projects", "limit": 5},
        )
        assert result.status_code == 200
        body = result.json()
        assert body["target_table"] == "sql_projects"
        assert body["columns"] == ["id", "content", "source_file"]
        assert body["rows"]
        assert body["rows"][0]["source_file"] == "sql.txt"


def test_sql_query_rejects_writes_and_unscoped_tables() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "SQL gate", "description": "Guard"}).json()["id"]
        empty = client.post(f"/datasets/{dataset_id}/sql-query", json={"sql": "select 1"})
        assert empty.status_code == 409

        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("guard.txt", b"Guard Project\nCAPEX 1 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "sql_guard_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "sql_guard_projects"},
        ).json()
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 200

        write = client.post(
            f"/datasets/{dataset_id}/sql-query",
            json={"plan_id": plan["id"], "sql": "update sql_guard_projects set content = 'bad'"},
        )
        assert write.status_code == 400
        unscoped = client.post(
            f"/datasets/{dataset_id}/sql-query",
            json={"plan_id": plan["id"], "sql": "select * from datasets"},
        )
        assert unscoped.status_code == 400


def test_sql_query_explains_unconfirmed_load_plan() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "SQL pending", "description": "Needs load"}).json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("pending.txt", b"Pending Project\nCAPEX 10 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "sql_pending_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "sql_pending_projects"},
        ).json()

        pending = client.post(
            f"/datasets/{dataset_id}/sql-query",
            json={"plan_id": plan["id"], "sql": "select * from sql_pending_projects"},
        )
        assert pending.status_code == 409
        assert pending.json()["detail"] == "Confirm the load plan before running SQL"


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
