from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_quality_scorecard_tracks_dataset_progression() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Scorecard", "description": "Quality gates"}).json()
        dataset_id = dataset["id"]
        empty = client.get(f"/datasets/{dataset_id}/quality-scorecard").json()
        assert empty["status"] == "pending"
        assert _check(empty, "extraction")["status"] == "pending"

        upload = client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("scorecard.txt", b"Project Delta\nCAPEX 42 USD\nYear 2026", "text/plain")},
        )
        assert upload.status_code == 200
        uploaded = client.get(f"/datasets/{dataset_id}/quality-scorecard").json()
        assert uploaded["status"] == "needs_attention"
        assert _check(uploaded, "extraction")["status"] == "attention"

        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs").json()
        _wait_job(client, job["id"])
        analyzed = client.get(f"/datasets/{dataset_id}/quality-scorecard").json()
        assert _check(analyzed, "gemma_summary")["status"] == "ready"
        assert _check(analyzed, "routing")["status"] == "attention"

        confirm_all_reviews(client, dataset_id, "scorecard_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "scorecard_projects"},
        ).json()
        preview = client.get(f"/datasets/{dataset_id}/quality-scorecard").json()
        assert _check(preview, "preview")["status"] == "ready"
        assert _check(preview, "source_references")["status"] == "ready"

        loaded = client.post(f"/load-plans/{plan['id']}/confirm")
        assert loaded.status_code == 200
        unverified = client.get(f"/datasets/{dataset_id}/quality-scorecard").json()
        assert unverified["status"] == "needs_attention"
        assert _check(unverified, "golden_answers")["status"] == "attention"

        created = client.post(
            f"/datasets/{dataset_id}/golden-checks",
            json={"question": "What is the CAPEX for Project Delta?", "expected_terms": ["Delta", "42", "USD"]},
        )
        assert created.status_code == 200
        assert client.post(f"/datasets/{dataset_id}/golden-checks/run").status_code == 200
        ready = client.get(f"/datasets/{dataset_id}/quality-scorecard").json()
        assert ready["status"] == "ready"
        assert ready["score"] >= 90
        assert _check(ready, "retrieval")["status"] == "ready"
        assert _check(ready, "golden_answers")["status"] == "ready"


def _check(payload: dict, key: str) -> dict:
    return next(check for check in payload["checks"] if check["key"] == key)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
