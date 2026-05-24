from fastapi.testclient import TestClient

from datarules_api.ai_summaries import document_ai_summary
from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import Dataset, Document, DocumentAiSummary, DocumentBlock


def test_ai_summary_cache_invalidates_when_blocks_change() -> None:
    with TestClient(app), SessionLocal() as db:
        dataset = Dataset(name="Summary cache", description="Fingerprint")
        db.add(dataset)
        db.flush()
        document = Document(
            dataset_id=dataset.id,
            file_name="summary.txt",
            file_type="text/plain",
            storage_path="/tmp/summary.txt",
            sha256="summary-cache-sha",
        )
        db.add(document)
        db.flush()
        first_block = DocumentBlock(document_id=document.id, block_type="paragraph", text="Alpha Project", confidence=0.95)
        second_block = DocumentBlock(document_id=document.id, block_type="paragraph", text="Beta Project", confidence=0.95)

        first = document_ai_summary(db, document, [first_block])
        cached = document_ai_summary(db, document, [first_block])
        second = document_ai_summary(db, document, [second_block])

        assert cached["source_fingerprint"] == first["source_fingerprint"]
        assert second["source_fingerprint"] != first["source_fingerprint"]
        assert "Alpha Project" in first["key_points"][0]
        assert "Beta Project" in second["key_points"][0]


def test_ai_summary_upserts_existing_document_row() -> None:
    with TestClient(app), SessionLocal() as db:
        dataset = Dataset(name="Summary upsert", description="Retry safe")
        db.add(dataset)
        db.flush()
        document = Document(
            dataset_id=dataset.id,
            file_name="upsert.txt",
            file_type="text/plain",
            storage_path="/tmp/upsert.txt",
            sha256="summary-upsert-sha",
        )
        db.add(document)
        db.flush()
        db.add(DocumentAiSummary(document_id=document.id, source_model="old", summary_json={"summary": "old"}))
        db.commit()
        block = DocumentBlock(document_id=document.id, block_type="paragraph", text="Retry Project", confidence=0.95)

        result = document_ai_summary(db, document, [block])
        rows = db.query(DocumentAiSummary).filter(DocumentAiSummary.document_id == document.id).all()

        assert len(rows) == 1
        assert rows[0].summary_json["source_fingerprint"] == result["source_fingerprint"]
        assert "Retry Project" in rows[0].summary_json["key_points"][0]
