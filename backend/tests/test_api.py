from time import sleep

from fastapi.testclient import TestClient
from sqlalchemy import text

from datarules_api.config import get_settings
from datarules_api.db import SessionLocal
from datarules_api.job_runner import recover_incomplete_jobs
from datarules_api.main import app
from datarules_api.models import IngestionJob, JobEvent
from helpers import confirm_all_reviews


def test_api_ingestion_smoke() -> None:
    with TestClient(app) as client:
        _run_smoke(client)


def test_api_ingestion_strips_nul_bytes() -> None:
    with TestClient(app) as client:
        created = client.post("/datasets", json={"name": "NUL dataset", "description": "Control chars"})
        dataset_id = created.json()["id"]
        upload = client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("nul.txt", b"Alpha\x00\nBeta", "text/plain")},
        )
        assert upload.status_code == 200

        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        assert job.status_code == 200
        current = _wait_job(client, job.json()["id"])
        assert current["status"] in {"waiting_review", "completed"}

        summaries = client.get(f"/datasets/{dataset_id}/document-summaries").json()
        assert summaries[0]["blocks"] == 1


def test_recover_incomplete_ingestion_job() -> None:
    with TestClient(app) as client:
        created = client.post("/datasets", json={"name": "Recovery dataset", "description": "Queued job"})
        dataset_id = created.json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("recover.txt", b"Recovery Project\nCAPEX 10 USD", "text/plain")},
        )
        with SessionLocal() as db:
            job = IngestionJob(dataset_id=dataset_id, total_files=1, status="queued")
            db.add(job)
            db.flush()
            db.add(JobEvent(job_id=job.id, stage="queued", message="Queued before restart", progress_percent=0))
            db.commit()
            job_id = job.id
        assert recover_incomplete_jobs() >= 1
        current = _wait_job(client, job_id)
        assert current["status"] in {"waiting_review", "completed"}
        assert current["attempt_count"] >= 1
        assert current["heartbeat_at"]


def test_load_plan_materializes_typed_sql_columns() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Typed dataset", "description": "Typed rows"})
        dataset_id = dataset.json()["id"]
        client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("typed.txt", b"Typed Project\nCAPEX 1 200 USD\nYear 2026", "text/plain")},
        )
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
        _wait_job(client, job.json()["id"])
        confirm_all_reviews(client, dataset_id, "typed_values_smoke")

        schema = {
            "target_columns": [
                {"name": "title", "type": "text", "required": False},
                {"name": "amount", "type": "numeric", "required": True},
                {"name": "year", "type": "integer", "required": False},
                {"name": "start_date", "type": "date", "required": False},
                {"name": "approved", "type": "boolean", "required": False},
            ],
        }
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "typed_values_smoke", "schema_json": schema},
        ).json()
        rows = plan["preview_rows"]
        rows[0]["field_values"].update(
            {"amount": "not-a-number", "year": "2026", "start_date": "23.02.2026", "approved": "да"}
        )
        invalid = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert invalid.json()["status"] == "blocked"
        assert any("type_invalid:amount:numeric" in row["validation_errors"] for row in invalid.json()["preview_rows"])

        rows = invalid.json()["preview_rows"]
        rows[0]["field_values"]["amount"] = "1 200 USD"
        valid = client.patch(f"/load-plans/{plan['id']}/preview-rows", json={"preview_rows": rows})
        assert valid.json()["status"] == "needs_confirmation"
        assert valid.json()["preview_rows"][0]["field_values"]["amount"] == "1200"

        confirmed = client.post(f"/load-plans/{plan['id']}/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "loaded"
        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT pg_typeof(amount)::text amount_type, amount, "
                    "pg_typeof(year)::text year_type, year, "
                    "pg_typeof(start_date)::text date_type, start_date, "
                    "pg_typeof(approved)::text approved_type, approved "
                    "FROM public.typed_values_smoke LIMIT 1"
                )
            ).mappings().one()
        assert row["amount_type"] == "numeric"
        assert str(row["amount"]) == "1200"
        assert row["year_type"] == "integer"
        assert row["year"] == 2026
        assert row["date_type"] == "date"
        assert row["start_date"].isoformat() == "2026-02-23"
        assert row["approved_type"] == "boolean"
        assert row["approved"] is True


def _run_smoke(client: TestClient) -> None:
    created = client.post(
        "/datasets",
        json={"name": "Smoke dataset", "description": "Investment documents"},
    )
    assert created.status_code == 200
    dataset_id = created.json()["id"]

    upload = client.post(
        f"/datasets/{dataset_id}/files",
        files={"files": ("sample.txt", b"Project Alpha\nCAPEX 1200 USD", "text/plain")},
    )
    assert upload.status_code == 200
    document_id = upload.json()[0]["id"]

    job = client.post(f"/datasets/{dataset_id}/ingestion-jobs")
    assert job.status_code == 200
    job_id = job.json()["id"]

    current = _wait_job(client, job_id)
    assert current["status"] in {"waiting_review", "completed"}

    reviews = client.get(f"/datasets/{dataset_id}/document-reviews")
    assert reviews.status_code == 200
    review = reviews.json()[0]
    assert review["doc_type_options"]
    assert review["table_options"]
    assert review["doc_type_options"][0]["reason"]
    assert "source" in review["table_options"][0]

    decision = client.post(
        f"/document-reviews/{review['id']}/decision",
            json={
                "selected_doc_type": review["doc_type_options"][0]["value"],
                "selected_table": "analysis_only_smoke",
                "notes": "Smoke confirmation",
            },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "confirmed"

    summaries = client.get(f"/datasets/{dataset_id}/document-summaries")
    assert summaries.status_code == 200
    assert summaries.json()[0]["blocks"] >= 1
    assert summaries.json()[0]["quality_profile"]["extraction_score"] > 0
    assert summaries.json()[0]["page_summaries"][0]["semantic_summary"]
    _assert_external_write_gate(client, dataset_id)

    chat = client.post(
        f"/datasets/{dataset_id}/schema-chat",
        json={"message": "I want a new projects table with amount and source references"},
    )
    assert chat.status_code == 200
    assert chat.json()["proposal_json"]

    plan = client.post(
        f"/datasets/{dataset_id}/load-plans",
        json={"target_mode": "new", "target_table": "analysis_only_smoke", "schema_json": chat.json()["proposal_json"]["schema_json"]},
    )
    assert plan.status_code == 200
    assert plan.json()["preview_rows"]
    assert plan.json()["preview_rows"][0]["field_values"]
    assert plan.json()["preview_rows"][0]["explainability"]["source_reference"]["block_id"]
    assert plan.json()["agent_preparation_json"]["stage"] == "planned"
    assert plan.json()["agent_preparation_json"]["retrieval"]["chunk_table"]
    plan_json = plan.json()
    assert plan_json["events"][0]["action"] == "created"
    assert next(iter(plan_json["preview_rows"][0]["field_sources"].values()))["block_id"]
    preview_rows = plan_json["preview_rows"]
    preview_rows[0]["field_values"]["name"] = "Project Alpha Edited"
    preview_rows[0]["content"] = "Project Alpha Edited: CAPEX 1200 USD"
    updated = client.patch(
        f"/load-plans/{plan_json['id']}/preview-rows",
        json={"preview_rows": preview_rows},
    )
    assert updated.status_code == 200
    assert updated.json()["preview_rows"][0]["edited_by_user"] is True
    assert updated.json()["preview_rows"][0]["field_values"]["name"] == "Project Alpha Edited"
    assert updated.json()["events"][-1]["action"] == "preview_edited"

    confirmed = client.post(f"/load-plans/{plan_json['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "loaded"
    assert confirmed.json()["agent_preparation_json"]["stage"] == "materialized"
    assert confirmed.json()["agent_preparation_json"]["inserted_records"] >= 1
    verification = confirmed.json()["agent_preparation_json"]["verification"]
    assert verification["target_table"]["exists"] is True
    assert verification["chunk_table"]["rows_for_plan"] >= 1
    assert verification["indexes"]["full_text"] is True
    assert confirmed.json()["events"][-1]["action"] == "loaded"
    confirmed_again = client.post(f"/load-plans/{plan_json['id']}/confirm")
    assert confirmed_again.status_code == 200
    loaded_events = [event for event in confirmed_again.json()["events"] if event["action"] == "loaded"]
    assert len(loaded_events) == 1

    search = client.post(f"/datasets/{dataset_id}/search", json={"query": "Project Alpha", "limit": 5})
    assert search.status_code == 200
    hits = search.json()
    assert hits
    agent_hit = next(hit for hit in hits if hit["block_type"] == "agent_chunk")
    assert agent_hit["match_source"] in {"bm25", "hybrid_rrf"}
    assert agent_hit["metadata"]["fusion"]["method"] == "rrf"
    assert agent_hit["metadata"]["rerank"]["method"] == "deterministic_v1" and "project" in agent_hit["metadata"]["rerank"]["matched_terms"]
    assert agent_hit["metadata"]["field_sources"]["name"]["block_id"]

    answer = client.post(f"/datasets/{dataset_id}/ask", json={"query": "What is Project Alpha?", "limit": 5})
    assert answer.status_code == 200
    assert answer.json()["answer_id"]
    assert answer.json()["citations"]
    assert answer.json()["answer"]
    history = client.get(f"/datasets/{dataset_id}/answers")
    assert history.status_code == 200
    assert history.json()[0]["query"] == "What is Project Alpha?"
    replay = client.post(f"/agent-answers/{answer.json()['answer_id']}/replay")
    assert replay.status_code == 200
    assert replay.json()["replay_of_answer_id"] == answer.json()["answer_id"]

    proposals = client.get(f"/datasets/{dataset_id}/schema-proposals")
    assert proposals.status_code == 200
    assert proposals.json()

    deleted = client.delete(f"/datasets/{dataset_id}/files/{document_id}")
    assert deleted.status_code == 200
    assert deleted.json()["removed_answers"] >= 2
    assert client.get(f"/datasets/{dataset_id}/files").json() == []
    assert client.get(f"/datasets/{dataset_id}/document-summaries").json() == []
    assert client.get(f"/datasets/{dataset_id}/answers").json() == []


def _assert_external_write_gate(client: TestClient, dataset_id: str) -> None:
    connection = client.post(
        "/database-connections",
        json={
            "name": "External read only",
            "description": "same server, external policy",
            "sqlalchemy_url": get_settings().database_url,
            "default_schema": "public",
        },
    )
    assert connection.status_code == 200
    connection_id = connection.json()["id"]
    assert connection.json()["capabilities_json"]["write_policy"]["enabled"] is False

    blocked = client.post(
        f"/datasets/{dataset_id}/load-plans",
        json={"connection_id": connection_id, "target_mode": "new", "target_table": "external_blocked"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked"
    assert any(issue["code"] == "write_not_allowed" for issue in blocked.json()["validation_issues"])
    assert client.post(f"/load-plans/{blocked.json()['id']}/confirm").status_code == 400

    unconfirmed = client.patch(
        f"/database-connections/{connection_id}/write-policy",
        json={"enabled": True, "schemas": ["public"]},
    )
    assert unconfirmed.status_code == 400

    wildcard = client.patch(
        f"/database-connections/{connection_id}/write-policy",
        json={"enabled": True, "schemas": ["*"], "confirm_external_write": True},
    )
    assert wildcard.status_code == 400

    enabled = client.patch(
        f"/database-connections/{connection_id}/write-policy",
        json={"enabled": True, "schemas": ["public"], "confirm_external_write": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["capabilities_json"]["write_policy"]["enabled"] is True

def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        if (payload := response.json())["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
