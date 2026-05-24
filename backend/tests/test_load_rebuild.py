from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_rebuild_preview_rechecks_current_document_route() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Rebuild", "description": "Preview recovery"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("rebuild.txt", b"Rebuild Project\nCAPEX 510 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "rebuild_target")

        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "rebuild_target"},
        ).json()
        assert plan["status"] == "needs_confirmation"
        review = client.get(f"/datasets/{dataset['id']}/document-reviews").json()[0]
        client.post(
            f"/document-reviews/{review['id']}/decision",
            json={"selected_doc_type": review["selected_doc_type"], "selected_table": "documents_raw", "notes": "reroute"},
        )

        mismatched = client.post(f"/load-plans/{plan['id']}/rebuild-preview")
        assert mismatched.status_code == 200
        assert mismatched.json()["status"] == "blocked"
        assert any(issue["code"] == "route_target_mismatch" for issue in mismatched.json()["validation_issues"])

        client.post(
            f"/document-reviews/{review['id']}/decision",
            json={"selected_doc_type": review["selected_doc_type"], "selected_table": "rebuild_target", "notes": "restore"},
        )
        rebuilt = client.post(f"/load-plans/{plan['id']}/rebuild-preview")
        assert rebuilt.status_code == 200
        body = rebuilt.json()
        assert body["status"] == "needs_confirmation"
        assert body["preview_rows"]
        assert not any(issue["code"] in {"routing_changed", "stale_preview", "route_target_mismatch"} for issue in body["validation_issues"])
        assert body["events"][-1]["action"] == "preview_rebuilt"


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed", "cancelled"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
