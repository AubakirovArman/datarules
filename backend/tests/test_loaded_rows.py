from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_loaded_rows_browser_reads_materialized_table_with_sources() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Rows", "description": "Loaded rows"}).json()
        dataset_id = dataset["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("rows.txt", b"Project Delta\nCAPEX 450 USD\nOwner KEGOC", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "loaded_rows_projects")

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "loaded_rows_projects"},
        ).json()
        not_loaded = client.get(f"/load-plans/{plan['id']}/rows")
        assert not_loaded.status_code == 400

        loaded = client.post(f"/load-plans/{plan['id']}/confirm")
        assert loaded.status_code == 200
        rows = client.get(f"/load-plans/{plan['id']}/rows?limit=5")
        assert rows.status_code == 200
        body = rows.json()
        assert body["destination"]["target_table"] == "loaded_rows_projects"
        assert body["total"] >= 1
        first = body["rows"][0]
        assert first["field_values"]
        assert first["source"]["document_id"]
        assert first["source"]["block_id"]
        assert first["source"]["file_name"] == "rows.txt"
        assert "Project Delta" in first["source"]["evidence"]


def test_loaded_rows_browser_is_scoped_to_one_load_plan() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Rows scope", "description": "Plan scoped"}).json()
        dataset_id = dataset["id"]
        upload = client.post(
            f"/datasets/{dataset_id}/files",
            files=[
                ("files", ("alpha.txt", b"Alpha Scope Project\nCAPEX 100 USD", "text/plain")),
                ("files", ("beta.txt", b"Beta Scope Project\nCAPEX 200 USD", "text/plain")),
            ],
        ).json()
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "row_scope_projects")

        first_plan = _loaded_plan(client, dataset_id, "row_scope_projects", [upload[0]["id"]])
        second_plan = _loaded_plan(client, dataset_id, "row_scope_projects", [upload[1]["id"]])

        first_rows = client.get(f"/load-plans/{first_plan['id']}/rows?limit=20").json()
        second_rows = client.get(f"/load-plans/{second_plan['id']}/rows?limit=20").json()
        assert first_rows["total"] == len(first_rows["rows"]) >= 1
        assert second_rows["total"] == len(second_rows["rows"]) >= 1
        assert {row["source"]["file_name"] for row in first_rows["rows"]} == {"alpha.txt"}
        assert {row["source"]["file_name"] for row in second_rows["rows"]} == {"beta.txt"}


def _loaded_plan(client: TestClient, dataset_id: str, table: str, document_ids: list[str]) -> dict:
    plan = client.post(
        f"/datasets/{dataset_id}/load-plans",
        json={"target_mode": "new", "target_table": table, "document_ids": document_ids},
    ).json()
    loaded = client.post(f"/load-plans/{plan['id']}/confirm")
    assert loaded.status_code == 200
    return loaded.json()


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
