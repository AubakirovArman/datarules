from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app


def test_accept_recommended_reviews_confirms_batch_and_invalidates_preview() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Batch review", "description": "Route all"}).json()
        dataset_id = dataset["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("batch.txt", b"Batch Project\nCAPEX 900 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "batch_projects"},
        ).json()
        assert plan["status"] == "blocked"
        assert any(issue["code"] == "unconfirmed_routes" for issue in plan["validation_issues"])

        accepted = client.post(f"/datasets/{dataset_id}/document-reviews/accept-recommended")
        assert accepted.status_code == 200
        assert accepted.json()
        assert all(review["status"] == "confirmed" for review in accepted.json())

        stale = client.get(f"/datasets/{dataset_id}/load-plans").json()[0]
        assert stale["id"] == plan["id"]
        assert stale["status"] == "blocked"
        assert any(issue["code"] == "routing_changed" for issue in stale["validation_issues"])
        assert stale["events"][-1]["action"] == "routing_changed"

        rebuilt = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "batch_projects"},
        )
        assert rebuilt.status_code == 200
        assert rebuilt.json()["status"] == "blocked"
        assert any(issue["code"] == "schema_not_approved" for issue in rebuilt.json()["validation_issues"])


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
