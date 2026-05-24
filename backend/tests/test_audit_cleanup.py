from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.config import get_settings
from datarules_api.connection_urls import set_connection_url
from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import DatabaseConnection, TableCatalog
from helpers import confirm_all_reviews


def test_audit_events_and_delete_cleanup_materialized_rows() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Audit cleanup", "description": "Deletion safety"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("cleanup.txt", b"Cleanup Project\nCAPEX 99 USD", "text/plain")},
        )
        assert upload.status_code == 200
        document_id = upload.json()[0]["id"]

        job = client.post(f"/datasets/{dataset['id']}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset["id"], "cleanup_materialized")
        plan = client.post(
            f"/datasets/{dataset['id']}/load-plans",
            json={"target_mode": "new", "target_table": "cleanup_materialized"},
        ).json()
        confirmed = client.post(f"/load-plans/{plan['id']}/confirm")
        assert confirmed.status_code == 200
        chunk_table = confirmed.json()["agent_preparation_json"]["chunk_table"]
        assert _count("cleanup_materialized", document_id) >= 1
        assert _count(chunk_table, document_id) >= 1

        deleted = client.delete(f"/datasets/{dataset['id']}/files/{document_id}")
        assert deleted.status_code == 200
        cleanup = deleted.json()["materialized_cleanup"]
        assert cleanup["target_rows"] >= 1
        assert cleanup["chunk_rows"] >= 1
        assert deleted.json()["invalidated_load_plans"]
        assert _count("cleanup_materialized", document_id) == 0
        assert _count(chunk_table, document_id) == 0
        plans = client.get(f"/datasets/{dataset['id']}/load-plans").json()
        invalidated = next(item for item in plans if item["id"] == plan["id"])
        assert invalidated["status"] == "blocked"
        assert invalidated["events"][-1]["action"] == "source_deleted"
        assert any(issue["code"] == "source_deleted" for issue in invalidated["validation_issues"])

        events = client.get(f"/datasets/{dataset['id']}/audit-events").json()
        actions = {event["action"] for event in events}
        assert {"dataset.created", "document.uploaded", "load_plan.loaded", "document.deleted"} <= actions
        assert "datarules:datarules" not in str(events)


def test_delete_survives_unreachable_external_cleanup_catalog() -> None:
    bad_url = "postgresql+psycopg://bad:secret@127.0.0.1:1/missing"
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Bad cleanup", "description": "External skip"}).json()
        upload = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("external.txt", b"External cleanup", "text/plain")},
        )
        document_id = upload.json()[0]["id"]
        connection = client.post(
            "/database-connections",
            json={
                "name": "Cleanup external",
                "description": "becomes unreachable",
                "sqlalchemy_url": get_settings().database_url,
                "default_schema": "public",
            },
        ).json()
        enabled = client.patch(
            f"/database-connections/{connection['id']}/write-policy",
            json={"enabled": True, "schemas": ["public"], "confirm_external_write": True},
        )
        assert enabled.status_code == 200
        with SessionLocal() as db:
            row = db.get(DatabaseConnection, connection["id"])
            assert row is not None
            set_connection_url(row, bad_url, encrypt=True)
            db.add(TableCatalog(connection_id=row.id, schema_name="public", table_name="ghost_rows", can_create_rows=True))
            db.commit()

        deleted = client.delete(f"/datasets/{dataset['id']}/files/{document_id}")
        assert deleted.status_code == 200
        cleanup = deleted.json()["materialized_cleanup"]
        failed = next(item for item in cleanup["details"] if item["target_table"] == "ghost_rows")
        assert failed["status"] == "skipped"
        assert "secret" not in failed["reason"]
        assert "***" in failed["reason"] or "connection" in failed["reason"].lower()


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
