from time import sleep

from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import DocumentAiSummary


def test_document_summaries_are_cached_per_requested_language() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Summary language", "description": "UI"}).json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("summary.txt", b"Investment project\nCAPEX 900 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])

        ru = client.get(f"/datasets/{dataset_id}/document-summaries?language=ru").json()[0]
        en = client.get(f"/datasets/{dataset_id}/document-summaries?language=en").json()[0]

        assert ru["ai_summary"]["requested_language"] == "ru"
        assert en["ai_summary"]["requested_language"] == "en"
        assert "извлечено" in ru["summary"]
        assert "extracted" in en["summary"]
        assert _summary_rows(ru["document_id"]) == 1
        assert _summary_variants(ru["document_id"]) == {"en", "ru"}


def _summary_rows(document_id: str) -> int:
    with SessionLocal() as db:
        return int(db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document_id).count())


def _summary_variants(document_id: str) -> set[str]:
    with SessionLocal() as db:
        row = db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document_id).first()
        variants = (row.summary_json or {}).get("_language_variants")
        return set(variants or {})


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
