from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_dataset_report_tracks_documents_routes_load_and_exports() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Report", "description": "Dataset report"}).json()
        dataset_id = dataset["id"]
        upload = client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("board.txt", b"Board Project\nCAPEX 800 USD\nYear 2026", "text/plain")},
        )
        document_id = upload.json()[0]["id"]
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])

        report = client.get(f"/datasets/{dataset_id}/report")
        assert report.status_code == 200
        body = report.json()
        assert body["status"] == "needs_routing"
        assert body["counts"]["documents"] == 1
        assert body["counts"]["blocks"] >= 1
        assert body["counts"]["ai_summaries"] == 1
        assert body["documents"][0]["id"] == document_id
        assert body["documents"][0]["route"]["recommended_table"]
        assert body["documents"][0]["canonical_json"].endswith(f"/files/{document_id}/canonical")

        canonical = client.get(f"/datasets/{dataset_id}/files/{document_id}/canonical")
        assert canonical.status_code == 200
        assert canonical.json()["document_id"] == document_id
        assert canonical.json()["blocks"]

        confirm_all_reviews(client, dataset_id, "dataset_report_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "dataset_report_projects"},
        ).json()
        loaded = client.post(f"/load-plans/{plan['id']}/confirm")
        assert loaded.status_code == 200

        ready = client.get(f"/datasets/{dataset_id}/report").json()
        assert ready["status"] == "ready_for_agent"
        assert ready["retrieval"]["ready"] is True
        assert ready["loading"][0]["loadable_rows"] >= 1
        assert ready["loading"][0]["agent"]["chunk_table"] == "dataset_report_projects_ai_chunks"


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
