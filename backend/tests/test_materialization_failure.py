from time import sleep

from fastapi.testclient import TestClient

from datarules_api import load_routes
from datarules_api.main import app
from helpers import confirm_all_reviews


def test_materialization_error_blocks_plan_without_500(monkeypatch) -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Failure gate", "description": "No 500"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("failure.txt", b"Failure Project\nCAPEX 500 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "failure_gate")
        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "failure_gate"},
        ).json()

        def fail_materialize(*_args, **_kwargs):
            raise RuntimeError("synthetic materialization failure")

        monkeypatch.setattr(load_routes, "materialize_load_plan", fail_materialize)
        failed = client.post(f"/load-plans/{plan['id']}/confirm")
        assert failed.status_code == 400

        plans = client.get(f"/datasets/{dataset['id']}/load-plans").json()
        blocked = next(item for item in plans if item["id"] == plan["id"])
        assert blocked["status"] == "blocked"
        assert blocked["events"][-1]["action"] == "materialization_failed"
        assert any(issue["code"] == "materialization_failed" for issue in blocked["validation_issues"])

        audit = client.get(f"/datasets/{dataset['id']}/audit-events").json()
        assert any(event["action"] == "load_plan.materialization_failed" for event in audit)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
