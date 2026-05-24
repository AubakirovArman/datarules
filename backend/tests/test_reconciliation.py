from time import sleep

from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import TableCatalog
from helpers import confirm_all_reviews


def test_dataset_reconciliation_detects_catalog_drift() -> None:
    with TestClient(app) as client:
        dataset_id = _loaded_dataset(client)
        report = client.get(f"/datasets/{dataset_id}/reconciliation").json()
        assert report["status"] == "ready"
        assert report["counts"]["loaded_plans"] == 1
        assert report["plans"][0]["catalog_issues"] == []

        _break_catalog(report["plans"][0]["target_table"])
        drifted = client.get(f"/datasets/{dataset_id}/reconciliation").json()
        assert drifted["status"] == "needs_attention"
        assert "catalog_chunk_table_mismatch" in drifted["plans"][0]["catalog_issues"]


def _loaded_dataset(client: TestClient) -> str:
    dataset_id = client.post("/datasets", json={"name": "Reconcile", "description": "Audit"}).json()["id"]
    client.post(
        f"/datasets/{dataset_id}/files",
        files={"files": ("reconcile.txt", b"Reconcile Project\nCAPEX 777 USD", "text/plain")},
    )
    job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
    _wait_job(client, job.json()["id"])
    confirm_all_reviews(client, dataset_id, "reconcile_projects")
    plan = client.post(
        f"/datasets/{dataset_id}/load-plans",
        json={"target_mode": "new", "target_table": "reconcile_projects"},
    ).json()
    assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 200
    return dataset_id


def _break_catalog(table: str) -> None:
    with SessionLocal() as db:
        row = db.query(TableCatalog).filter(TableCatalog.table_name == table).first()
        row.agent_profile_json = {**(row.agent_profile_json or {}), "chunk_table": "wrong_chunks"}
        db.commit()


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
