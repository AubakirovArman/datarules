from fastapi.testclient import TestClient

from datarules_api.config import get_settings
from datarules_api.main import app


def test_duplicate_upload_reuses_existing_document() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Duplicate upload", "description": "Checksum"}).json()
        first = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("same.txt", b"Same content", "text/plain")},
        )
        second = client.post(
            f"/datasets/{dataset['id']}/files",
            files={"files": ("same-copy.txt", b"Same content", "text/plain")},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()[0]["id"] == first.json()[0]["id"]
        assert len(client.get(f"/datasets/{dataset['id']}/files").json()) == 1
        audit = client.get(f"/datasets/{dataset['id']}/audit-events").json()
        assert any(event["action"] == "document_upload.duplicate" for event in audit)


def test_upload_rejects_unsupported_type_and_oversized_file() -> None:
    settings = get_settings()
    old_limit = settings.max_upload_mb
    settings.max_upload_mb = 1
    try:
        with TestClient(app) as client:
            dataset = client.post("/datasets", json={"name": "Upload policy", "description": "Guards"}).json()
            unsupported = client.post(
                f"/datasets/{dataset['id']}/files",
                files={"files": ("program.exe", b"MZ", "application/octet-stream")},
            )
            assert unsupported.status_code == 400
            too_large = client.post(
                f"/datasets/{dataset['id']}/files",
                files={"files": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
            )
            assert too_large.status_code == 400
            assert client.get(f"/datasets/{dataset['id']}/files").json() == []
            audit = client.get(f"/datasets/{dataset['id']}/audit-events").json()
            rejected = [event for event in audit if event["action"] == "document_upload.rejected"]
            assert {event["payload_json"]["code"] for event in rejected} == {"unsupported_file_type", "file_too_large"}
    finally:
        settings.max_upload_mb = old_limit
