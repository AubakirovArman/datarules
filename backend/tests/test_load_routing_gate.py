from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app


def test_load_plan_requires_confirmed_document_routing() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Routing gate", "description": "Confirm first"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("route.txt", b"Route Project\nCAPEX 700 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])

        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "routing_gate"},
        )
        assert plan.status_code == 200
        body = plan.json()
        assert body["status"] == "blocked"
        issue = next(item for item in body["validation_issues"] if item["code"] == "unconfirmed_routes")
        assert issue["severity"] == "error"
        assert client.post(f"/load-plans/{body['id']}/confirm").status_code == 400


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
