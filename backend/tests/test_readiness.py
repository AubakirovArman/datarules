from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_dataset_readiness_tracks_full_flow() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Readiness", "description": "Flow state"}).json()
        dataset_id = dataset["id"]
        assert _stage(client.get(f"/datasets/{dataset_id}/readiness").json(), "upload")["status"] == "pending"

        upload = client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("readiness.txt", b"Project Alpha\nCAPEX 1200 USD", "text/plain")},
        )
        assert upload.status_code == 200
        uploaded = client.get(f"/datasets/{dataset_id}/readiness").json()
        assert _stage(uploaded, "upload")["status"] == "ready"
        assert _stage(uploaded, "extraction")["status"] == "pending"
        assert uploaded["action_plan"][0]["code"] == "run_extraction"

        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs").json()
        _wait_job(client, job["id"])
        analyzed = client.get(f"/datasets/{dataset_id}/readiness").json()
        assert _stage(analyzed, "extraction")["status"] == "ready"
        assert _stage(analyzed, "summary")["status"] == "ready"
        assert _stage(analyzed, "routing")["status"] == "attention"
        assert analyzed["action_plan"][0]["code"] == "confirm_routing"
        confirm_all_reviews(client, dataset_id, "readiness_probe")

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "readiness_probe"},
        ).json()
        previewed = client.get(f"/datasets/{dataset_id}/readiness").json()
        assert plan["preview_rows"]
        assert _stage(previewed, "preview")["status"] == "ready"

        confirmed = client.post(f"/load-plans/{plan['id']}/confirm")
        assert confirmed.status_code == 200
        ready = client.get(f"/datasets/{dataset_id}/readiness").json()
        assert ready["agent"]["ready"] is True
        assert ready["action_plan"][0]["code"] == "ready_for_agent"
        assert ready["agent"]["tables"][0]["chunk_table"] == "readiness_probe_ai_chunks"
        assert _stage(ready, "materialization")["status"] == "ready"
        assert _stage(ready, "retrieval")["status"] == "ready"


def _stage(payload: dict, key: str) -> dict:
    return next(stage for stage in payload["stages"] if stage["key"] == key)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
