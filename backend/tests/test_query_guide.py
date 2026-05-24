from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_query_guide_tracks_loaded_tables_fields_and_modes() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Guide", "description": "Query guide"}).json()
        dataset_id = dataset["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("guide.txt", b"Project Guide\nCAPEX 900 USD\nYear 2026", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "guide_projects")
        schema = {"target_columns": [{"name": "project_name", "type": "text"}, {"name": "amount", "type": "numeric"}]}
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "guide_projects", "schema_json": schema},
        ).json()
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 200

        guide = client.get(f"/datasets/{dataset_id}/query-guide?language=ru")
        assert guide.status_code == 200
        body = guide.json()
        assert body["status"] == "ready_for_agent"
        assert body["tables"][0]["table"] == "guide_projects"
        assert {field["name"] for field in body["fields"]} >= {"project_name", "amount"}
        assert {item["name"] for item in body["filters"]} >= {"amount", "source_file", "target_table"}
        modes = {item["mode"]: item["ready"] for item in body["search_modes"]}
        assert modes["sql"] is True
        assert modes["hybrid"] is True
        assert any("CAPEX" in example["question"] for example in body["examples"])


def test_query_guide_for_empty_dataset_returns_next_action() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Empty guide", "description": ""}).json()["id"]
        body = client.get(f"/datasets/{dataset_id}/query-guide?language=en").json()
        assert body["status"] == "upload_documents"
        assert body["next_actions"] == ["readiness_next_upload"]


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
