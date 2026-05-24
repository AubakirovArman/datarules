from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import TableCatalog
from helpers import confirm_all_reviews


def test_existing_target_blocks_missing_source_columns() -> None:
    with TestClient(app) as client:
        dataset_id = _ready_dataset(client, "Existing source gate", "existing_bad_source")
        connection_id = _internal_connection(client)
        _create_table(
            "existing_bad_source",
            "id text PRIMARY KEY, title text",
            connection_id,
            [{"name": "title", "type": "text"}],
        )

        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"connection_id": connection_id, "target_mode": "existing", "target_table": "existing_bad_source"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "blocked"
        issue = _issue(body, "target_missing_source_columns")
        assert "content" in issue["columns"]
        assert "source_document_id" in issue["columns"]


def test_existing_target_blocks_missing_schema_columns() -> None:
    with TestClient(app) as client:
        dataset_id = _ready_dataset(client, "Existing data gate", "existing_missing_data")
        connection_id = _internal_connection(client)
        _create_table(
            "existing_missing_data",
            """
            id text PRIMARY KEY,
            content text,
            source_document_id text,
            source_block_id text,
            field_values jsonb NOT NULL DEFAULT '{}'::jsonb
            """,
            connection_id,
            [{"name": "title", "type": "text"}],
        )

        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"connection_id": connection_id, "target_mode": "existing", "target_table": "existing_missing_data"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "blocked"
        assert _issue(body, "target_missing_data_columns")["columns"] == ["title"]


def test_confirm_rechecks_existing_target_after_table_drift() -> None:
    with TestClient(app) as client:
        dataset_id = _ready_dataset(client, "Existing drift gate", "existing_drift")
        connection_id = _internal_connection(client)
        _create_table("existing_drift", _compatible_columns("title text"), connection_id, [{"name": "title", "type": "text"}])

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"connection_id": connection_id, "target_mode": "existing", "target_table": "existing_drift"},
        ).json()
        assert plan["status"] == "needs_confirmation"
        _drop_column("existing_drift", "content")

        response = client.post(f"/load-plans/{plan['id']}/confirm")

        assert response.status_code == 400
        blocked = client.get(f"/datasets/{dataset_id}/load-plans").json()[0]
        assert blocked["status"] == "blocked"
        assert blocked["events"][-1]["action"] == "preflight_failed"
        assert _issue(blocked, "target_missing_source_columns")["columns"] == ["content"]


def test_existing_target_warns_on_schema_type_mismatch() -> None:
    with TestClient(app) as client:
        dataset_id = _ready_dataset(client, "Existing type gate", "existing_type_mismatch")
        connection_id = _internal_connection(client)
        _create_table(
            "existing_type_mismatch",
            _compatible_columns("amount text"),
            connection_id,
            [{"name": "amount", "type": "numeric"}],
        )

        response = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={
                "connection_id": connection_id,
                "target_mode": "existing",
                "target_table": "existing_type_mismatch",
                "schema_json": {"target_columns": [{"name": "amount", "type": "numeric"}]},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "needs_confirmation"
        issue = _issue(body, "target_type_mismatch")
        assert issue["severity"] == "warning"
        assert issue["columns"] == [{"column": "amount", "expected": "numeric", "actual": "text"}]


def _ready_dataset(client: TestClient, name: str, table: str) -> str:
    dataset_id = client.post("/datasets", json={"name": name, "description": "Compatibility"}).json()["id"]
    client.post(
        f"/datasets/{dataset_id}/files",
        files={"files": ("compat.txt", b"Compatibility Project\nCAPEX 100 USD", "text/plain")},
    )
    job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
    _wait_job(client, job.json()["id"])
    confirm_all_reviews(client, dataset_id, table)
    return dataset_id


def _internal_connection(client: TestClient) -> str:
    return next(item["id"] for item in client.get("/database-connections").json() if item["is_internal"])


def _create_table(table: str, columns_sql: str, connection_id: str, columns_json: list[dict]) -> None:
    with SessionLocal() as db:
        db.execute(text(f'DROP TABLE IF EXISTS public."{table}"'))
        db.execute(text(f'CREATE TABLE public."{table}" ({columns_sql})'))
        db.add(TableCatalog(
            connection_id=connection_id,
            schema_name="public",
            table_name=table,
            description="Compatibility test table",
            columns_json=columns_json,
        ))
        db.commit()


def _compatible_columns(extra: str) -> str:
    return f"""
    id text PRIMARY KEY,
    content text,
    source_document_id text,
    source_block_id text,
    field_values jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    {extra}
    """


def _drop_column(table: str, column: str) -> None:
    with SessionLocal() as db:
        db.execute(text(f'ALTER TABLE public."{table}" DROP COLUMN "{column}"'))
        db.commit()


def _issue(body: dict, code: str) -> dict:
    return next(issue for issue in body["validation_issues"] if issue["code"] == code)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
