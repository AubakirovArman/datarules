from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import AuditEvent, Dataset, IngestionJob


def test_diagnostics_reports_runtime_checks() -> None:
    with TestClient(app) as client:
        response = client.get("/diagnostics")
        assert response.status_code == 200
        payload = response.json()
        checks = {item["key"]: item for item in payload["checks"]}
        assert payload["status"] in {"ok", "attention"}
        assert checks["database"]["status"] in {"ok", "warning"}
        assert checks["storage"]["status"] == "ok"
        assert checks["gemma"]["status"] == "disabled"
        assert checks["embeddings"]["status"] == "disabled"
        assert "secret_storage" in checks
        assert checks["ingestion_runner"]["status"] == "ok"
        assert payload["runtime"]["gemma_gpu_id"] == 2


def test_diagnostics_warns_about_stale_ingestion_jobs() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Stale diag", "description": "Monitor"}).json()
        with SessionLocal() as db:
            job = IngestionJob(
                dataset_id=dataset["id"],
                status="running",
                current_stage="schema_inference",
                heartbeat_at=datetime.utcnow() - timedelta(hours=1),
            )
            db.add(job)
            db.commit()
        payload = client.get("/diagnostics").json()
        checks = {item["key"]: item for item in payload["checks"]}
        assert checks["ingestion_runner"]["status"] == "warning"
        assert checks["ingestion_runner"]["details"]["stale"] >= 1
        with SessionLocal() as db:
            db.query(IngestionJob).filter(IngestionJob.dataset_id == dataset["id"]).delete()
            db.query(AuditEvent).filter(AuditEvent.dataset_id == dataset["id"]).delete()
            db.query(Dataset).filter(Dataset.id == dataset["id"]).delete()
            db.commit()
