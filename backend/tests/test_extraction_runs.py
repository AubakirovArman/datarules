from pathlib import Path

from datarules_api.db import SessionLocal, init_db
from datarules_api.extraction_runs import backfill_missing_extraction_runs
from datarules_api.models import Dataset, Document, DocumentBlock, DocumentExtractionRun


def test_backfill_missing_extraction_runs_creates_legacy_snapshot() -> None:
    init_db()
    with SessionLocal() as db:
        dataset = Dataset(name="Legacy", description="Backfill")
        db.add(dataset)
        db.flush()
        document = Document(
            dataset_id=dataset.id,
            file_name="legacy.txt",
            file_type="text/plain",
            storage_path="missing-legacy.txt",
            sha256="a" * 64,
            status="extracted",
        )
        db.add(document)
        db.flush()
        db.add(DocumentBlock(document_id=document.id, block_type="paragraph", text="Legacy text", confidence=0.98))
        db.commit()
        document_id = document.id

    assert backfill_missing_extraction_runs() >= 1

    with SessionLocal() as db:
        run = db.query(DocumentExtractionRun).filter(DocumentExtractionRun.document_id == document_id).one()
        assert run.run_type == "legacy_import"
        assert run.metrics_json["blocks"] == 1
        assert Path(run.canonical_path).exists()
