from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_load_plan_report_rechecks_loaded_agent_tables() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Report dataset", "description": "Post load"}).json()
        dataset_id = dataset["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("report.txt", b"Report Project\nCAPEX 300 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "report_projects")

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "report_projects"},
        ).json()
        planned = client.get(f"/load-plans/{plan['id']}/report")
        assert planned.status_code == 200
        assert planned.json()["live_verification"] is None
        row_id = plan["preview_rows"][0]["row_id"]
        source = client.get(f"/load-plans/{plan['id']}/preview-rows/{row_id}/source")
        assert source.status_code == 200
        assert source.json()["document"]["file_name"] == "report.txt"
        assert "Report Project" in source.json()["block"]["text"]
        assert source.json()["warnings"] == []

        loaded = client.post(f"/load-plans/{plan['id']}/confirm")
        assert loaded.status_code == 200
        report = client.get(f"/load-plans/{plan['id']}/report")
        assert report.status_code == 200
        body = report.json()
        assert body["destination"]["target_table"] == "report_projects"
        assert body["preview"]["loadable_rows"] >= 1
        assert body["exports"]["csv"].endswith("/export.csv")
        assert body["live_verification"]["target_table"]["exists"] is True
        assert body["live_verification"]["indexes"]["full_text"] is True


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
