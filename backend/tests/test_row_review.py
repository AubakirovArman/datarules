from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.db import SessionLocal
from datarules_api.main import app
from helpers import confirm_all_reviews


def test_rejected_preview_rows_are_not_loaded_or_indexed() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Row review", "description": "Approve reject"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files=[
                ("files", ("keep.txt", b"Keep Project\nCAPEX 100 USD", "text/plain")),
                ("files", ("drop.txt", b"Drop Project\nCAPEX 200 USD", "text/plain")),
            ],
        )
        assert upload.status_code == 200
        docs = upload.json()
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "row_review_gate")

        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "row_review_gate"},
        ).json()
        rows = plan["preview_rows"]
        for row in rows:
            row["row_status"] = "rejected" if row["source_document_id"] == docs[1]["id"] else "approved"
        updated = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert updated.status_code == 200
        assert any(issue["code"] == "rejected_rows" for issue in updated.json()["validation_issues"])
        quarantine = client.get(f"/load-plans/{plan['id']}/quarantine")
        assert quarantine.status_code == 200
        assert quarantine.json()["summary"]["quarantined_rows"] == 1
        assert quarantine.json()["rows"][0]["source_document_id"] == docs[1]["id"]
        assert "rejected" in quarantine.json()["rows"][0]["reasons"]

        confirmed = client.post(f"/load-plans/{plan['id']}/confirm")
        assert confirmed.status_code == 200
        readiness = confirmed.json()["agent_preparation_json"]
        assert readiness["inserted_records"] == 1
        assert readiness["inserted_chunks"] == 1
        assert _count("row_review_gate", docs[0]["id"]) == 1
        assert _count("row_review_gate", docs[1]["id"]) == 0
        assert _count(readiness["chunk_table"], docs[0]["id"]) == 1
        assert _count(readiness["chunk_table"], docs[1]["id"]) == 0


def test_needs_review_row_must_be_approved_before_loading() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Needs review", "description": "Gate"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("uncertain.txt", b"Uncertain Project\nCAPEX 300 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "needs_review_gate")
        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "needs_review_gate"},
        ).json()
        rows = plan["preview_rows"]
        rows[0]["row_status"] = "needs_review"
        rows[0]["confidence"] = 0.51
        blocked = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "blocked"
        assert any(issue["code"] == "no_loadable_rows" for issue in blocked.json()["validation_issues"])
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 400

        rows = blocked.json()["preview_rows"]
        rows[0]["row_status"] = "approved"
        approved = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert approved.status_code == 200
        assert approved.json()["status"] == "needs_confirmation"
        confirmed = client.post(f"/load-plans/{plan['id']}/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["agent_preparation_json"]["inserted_records"] == 1


def test_invalid_source_reference_blocks_loading_and_enters_quarantine() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Broken source", "description": "Gate"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("broken-source.txt", b"Broken Source Project\nCAPEX 400 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "broken_source_gate")
        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "broken_source_gate"},
        ).json()
        rows = plan["preview_rows"]
        rows[0]["row_status"] = "approved"
        rows[0]["source_block_id"] = "blk_missing_for_test"
        updated = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert updated.status_code == 200
        assert updated.json()["status"] == "blocked"
        assert any(issue["code"] == "source_reference_invalid" for issue in updated.json()["validation_issues"])
        quarantine = client.get(f"/load-plans/{plan['id']}/quarantine").json()
        assert quarantine["summary"]["quarantined_rows"] == 1
        assert "source:source_block_not_found" in quarantine["rows"][0]["reasons"]
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 400


def test_unknown_preview_field_blocks_loading_and_enters_quarantine() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Schema mismatch", "description": "Gate"}).json()
        client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("schema-mismatch.txt", b"Schema Mismatch Project\nCAPEX 500 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "schema_mismatch_gate")
        schema = {"target_columns": [{"name": "title", "type": "text", "required": False}]}
        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "schema_mismatch_gate", "schema_json": schema},
        ).json()
        rows = plan["preview_rows"]
        rows[0]["row_status"] = "approved"
        rows[0]["field_values"]["not_in_schema"] = "must not write silently"
        updated = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert updated.status_code == 200
        assert updated.json()["status"] == "blocked"
        assert "unknown_field:not_in_schema" in updated.json()["preview_rows"][0]["validation_errors"]
        quarantine = client.get(f"/load-plans/{plan['id']}/quarantine").json()
        assert "validation:unknown_field:not_in_schema" in quarantine["rows"][0]["reasons"]
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 400


def _count(table: str, document_id: str) -> int:
    with SessionLocal() as db:
        return int(
            db.execute(
                text(f'SELECT count(*) FROM public."{table}" WHERE source_document_id = :document_id'),
                {"document_id": document_id},
            ).scalar()
            or 0
        )


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
