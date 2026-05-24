from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app


def test_load_plan_can_scope_to_selected_documents() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Scoped dataset", "description": "Two docs"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files=[
                ("files", ("alpha.txt", b"Alpha Project\nCAPEX 100 USD", "text/plain")),
                ("files", ("beta.txt", b"Beta Project\nCAPEX 200 USD", "text/plain")),
            ],
        )
        assert upload.status_code == 200
        documents = upload.json()
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])

        beta_id = documents[1]["id"]
        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={
                "target_mode": "new",
                "target_table": "scoped_beta_only",
                "document_ids": [beta_id],
            },
        )
        assert plan.status_code == 200
        body = plan.json()
        assert body["schema_json"]["document_scope"]["document_ids"] == [beta_id]
        assert body["schema_json"]["source_snapshot"]["fingerprint"]
        assert body["preview_rows"]
        assert {row["source_document_id"] for row in body["preview_rows"]} == {beta_id}
        assert all("Beta" in row["content"] or row["source_file"] == "beta.txt" for row in body["preview_rows"])

        reviews = client.get(f"/datasets/{dataset['id']}/document-reviews").json()
        beta_review = next(review for review in reviews if review["document_id"] == beta_id)
        decision = client.post(
            f"/document-reviews/{beta_review['id']}/decision",
            json={
                "selected_doc_type": beta_review["doc_type_options"][0]["value"],
                "selected_table": "documents_raw",
                "notes": "Changed after preview",
            },
        )
        assert decision.status_code == 200
        blocked = client.post(f"/load-plans/{body['id']}/confirm")
        assert blocked.status_code == 400
        plans = client.get(f"/datasets/{dataset['id']}/load-plans").json()
        stale = next(item for item in plans if item["id"] == body["id"])
        assert stale["status"] == "blocked"
        assert any(issue["code"] == "stale_preview" for issue in stale["validation_issues"])
        assert stale["events"][-1]["action"] == "stale_preview"


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
