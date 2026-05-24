from time import sleep

from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import IngestionJob, JobEvent


def test_cancel_queued_ingestion_unlocks_file_changes() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Cancel flow", "description": "Stop analysis"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("cancel.txt", b"Project Cancel\nCAPEX 10 USD", "text/plain")},
        ).json()
        job_id = _queued_job(dataset["id"])

        locked = client.delete(f"/datasets/{dataset['id']}/files/{upload[0]['id']}")
        assert locked.status_code == 409

        response = client.post(f"/jobs/{job_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] in {"cancelling", "cancelled"}
        assert _wait_job(client, job_id)["status"] == "cancelled"

        unlocked = client.delete(f"/datasets/{dataset['id']}/files/{upload[0]['id']}")
        assert unlocked.status_code == 200


def _queued_job(dataset_id: str) -> str:
    with SessionLocal() as db:
        job = IngestionJob(dataset_id=dataset_id, total_files=1, status="queued")
        db.add(job)
        db.flush()
        db.add(JobEvent(job_id=job.id, stage="queued", message="Manual queue", progress_percent=0))
        db.commit()
        return job.id


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed", "cancelled"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
