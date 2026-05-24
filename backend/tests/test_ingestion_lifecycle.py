from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.job_runner import recover_incomplete_jobs
from datarules_api.main import app
from datarules_api.models import IngestionJob


def test_start_job_reuses_active_dataset_job() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Active reuse", "description": "Double click"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("active.txt", b"Active Project\nCAPEX 11 USD", "text/plain")},
        )
        active_id = _queued_job(dataset["id"])

        response = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        assert response.status_code == 200
        assert response.json()["id"] == active_id
        assert _job_count(dataset["id"]) == 1


def test_files_are_locked_while_ingestion_is_active() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Locked files", "description": "No races"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("locked.txt", b"Locked Project\nCAPEX 22 USD", "text/plain")},
        )
        document_id = upload.json()[0]["id"]
        _queued_job(dataset["id"])

        second_upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("new.txt", b"New Project", "text/plain")},
        )
        delete = client.delete(f"/datasets/{dataset['id']}/files/{document_id}")
        assert second_upload.status_code == 409
        assert delete.status_code == 409
        assert len(client.get(f"/datasets/{dataset['id']}/files").json()) == 1


def test_recovery_fails_jobs_after_retry_limit() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Retry limit", "description": "Hard stop"}).json()
        job_id = _queued_job(dataset["id"], attempt_count=3, max_attempts=3)
        recover_incomplete_jobs()
        current = client.get(f"/jobs/{job_id}").json()
        assert current["status"] == "failed"
        assert current["error_message"] == "Job retry limit was reached during startup recovery."


def _queued_job(dataset_id: str, attempt_count: int = 0, max_attempts: int = 3) -> str:
    with SessionLocal() as db:
        job = IngestionJob(
            dataset_id=dataset_id,
            total_files=1,
            status="queued",
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )
        db.add(job)
        db.commit()
        return job.id


def _job_count(dataset_id: str) -> int:
    with SessionLocal() as db:
        return db.query(IngestionJob).filter(IngestionJob.dataset_id == dataset_id).count()
