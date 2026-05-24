from time import sleep

from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import LoadPlan, TableCatalog
from helpers import confirm_all_reviews


def test_load_plan_rejects_unsafe_target_identifiers() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Identifier gate", "description": "Names"}).json()["id"]
        bad_table = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "Bad Table"},
        )
        assert bad_table.status_code == 400
        assert "target_table" in bad_table.json()["detail"]

        long_schema = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"schema_name": "a" * 64, "target_mode": "new", "target_table": "safe_table"},
        )
        assert long_schema.status_code == 400
        assert "schema_name" in long_schema.json()["detail"]


def test_load_plan_rejects_reserved_duplicate_and_unsafe_columns() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Column gate", "description": "Columns"}).json()["id"]
        schema = {
            "target_columns": [
                {"name": "project_name", "type": "text"},
                {"name": "project_name", "type": "text"},
                {"name": "content", "type": "text"},
                {"name": "Bad Column", "type": "text"},
            ],
        }
        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "safe_table", "schema_json": schema},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Duplicate target column" in detail
        assert "managed by DataRules" in detail
        assert "target_columns must be snake_case" in detail


def test_valid_identifiers_still_create_preview_plan() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Valid gate", "description": "Safe"}).json()["id"]
        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={
                "schema_name": "public",
                "target_mode": "new",
                "target_table": "safe_projects",
                "schema_json": {"target_columns": [{"name": "project_name", "type": "text"}]},
            },
        )
        assert response.status_code == 200
        assert response.json()["target_table"] == "safe_projects"


def test_catalog_generated_schema_identifier_errors_block_preview() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Catalog gate", "description": "Generated schema"}).json()["id"]
        connection_id = next(item["id"] for item in client.get("/database-connections").json() if item["is_internal"])
        with SessionLocal() as db:
            db.add(TableCatalog(
                connection_id=connection_id,
                schema_name="public",
                table_name="catalog_bad_columns",
                description="Bad generated columns",
                columns_json=[
                    {"name": "Bad Column", "type": "text"},
                    {"name": "project_name", "type": "text"},
                    {"name": "project_name", "type": "text"},
                ],
            ))
            db.commit()

        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={
                "connection_id": connection_id,
                "schema_name": "public",
                "target_mode": "existing",
                "target_table": "catalog_bad_columns",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "blocked"
        codes = {issue["code"] for issue in body["validation_issues"]}
        assert "invalid_column_identifier" in codes
        assert "duplicate_target_column" in codes


def test_manual_table_catalog_rejects_unsafe_names_but_allows_managed_metadata() -> None:
    with TestClient(app) as client:
        connection_id = next(item["id"] for item in client.get("/database-connections").json() if item["is_internal"])
        bad = client.post(
            "/table-catalog",
            json={
                "connection_id": connection_id,
                "schema_name": "public",
                "table_name": "Bad Table",
                "columns_json": [{"name": "Bad Column", "type": "text"}],
            },
        )
        assert bad.status_code == 400
        assert "target_table" in bad.json()["detail"] or "Catalog column" in bad.json()["detail"]

        good = client.post(
            "/table-catalog",
            json={
                "connection_id": connection_id,
                "schema_name": "public",
                "table_name": "safe_catalog_table",
                "columns_json": [{"name": "content", "type": "text"}, {"name": "project_name", "type": "text"}],
            },
        )
        assert good.status_code == 200
        assert good.json()["table_name"] == "safe_catalog_table"


def test_confirm_blocks_existing_plan_with_corrupted_schema_identifiers() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Corrupt schema", "description": "Guard"}).json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("guard.txt", b"Guard Project\nCAPEX 100 USD", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "guard_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "guard_projects"},
        ).json()
        with SessionLocal() as db:
            row = db.get(LoadPlan, plan["id"])
            row.schema_json = {**row.schema_json, "target_columns": [{"name": "Bad Column", "type": "text"}]}
            row.validation_issues = []
            row.status = "needs_confirmation"
            db.commit()

        response = client.post(f"/load-plans/{plan['id']}/confirm")
        assert response.status_code == 400
        blocked = client.get(f"/datasets/{dataset_id}/load-plans").json()[0]
        assert blocked["status"] == "blocked"
        assert blocked["events"][-1]["action"] == "schema_identifier_error"
        assert any(issue["code"] == "invalid_column_identifier" for issue in blocked["validation_issues"])


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
