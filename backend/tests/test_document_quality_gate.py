from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import Dataset, Document, DocumentBlock, DocumentReview
from helpers import approve_test_schema


def test_document_quality_report_flags_blocked_document() -> None:
    with TestClient(app) as client:
        dataset_id, document_id = _bad_document("quality_report_target")

        response = client.get(f"/datasets/{dataset_id}/document-quality")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "blocked"
        assert body["counts"]["blocked"] == 1
        assert body["documents"][0]["document_id"] == document_id
        assert body["documents"][0]["load_gate"] == "blocked"
        assert set(body["documents"][0]["actions"]) >= {"rerun_extraction", "review_ocr"}


def test_load_plan_blocks_document_with_bad_extraction_quality() -> None:
    with TestClient(app) as client:
        dataset_id, _ = _bad_document("quality_blocked_target")
        approve_test_schema(client, dataset_id, "quality_blocked_target")

        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "quality_blocked_target"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "blocked"
        assert any(issue["code"] == "document_quality_blocked" for issue in body["validation_issues"])


def _bad_document(table: str) -> tuple[str, str]:
    with SessionLocal() as db:
        dataset = Dataset(name=f"Quality {table}", description="Bad extraction")
        db.add(dataset)
        db.flush()
        document = Document(
            dataset_id=dataset.id,
            file_name=f"{table}.pdf",
            file_type="application/pdf",
            storage_path="/tmp/missing.pdf",
            sha256=f"{table}-sha",
            status="extracted",
        )
        db.add(document)
        db.flush()
        db.add(DocumentBlock(document_id=document.id, block_type="image_page", text="", page=1, confidence=0.2))
        db.add(DocumentReview(dataset_id=dataset.id, document_id=document.id, status="confirmed", selected_doc_type="raw_reference", selected_table=table))
        db.commit()
        return dataset.id, document.id
