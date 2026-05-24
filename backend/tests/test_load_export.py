from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_loaded_plan_exports_only_plan_rows() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Export dataset", "description": "CSV and JSON"}).json()
        dataset_id = dataset["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("export.txt", b"Export Project\nCAPEX 420 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "export_projects")

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "export_projects"},
        ).json()
        blocked_export = client.get(f"/load-plans/{plan['id']}/export.json")
        assert blocked_export.status_code == 400

        loaded = client.post(f"/load-plans/{plan['id']}/confirm")
        assert loaded.status_code == 200
        plan_id = loaded.json()["id"]

        json_export = client.get(f"/load-plans/{plan_id}/export.json")
        assert json_export.status_code == 200
        json_rows = json_export.json()["rows"]
        assert len(json_rows) == len(loaded.json()["preview_rows"])
        assert json_rows[0]["content"]
        assert json_rows[0]["field_values"]

        csv_export = client.get(f"/load-plans/{plan_id}/export.csv")
        assert csv_export.status_code == 200
        assert "text/csv" in csv_export.headers["content-type"]
        assert "content" in csv_export.text.splitlines()[0]
        assert "Export Project" in csv_export.text


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
