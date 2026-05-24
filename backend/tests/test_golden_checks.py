from time import sleep

from fastapi.testclient import TestClient

from datarules_api.main import app
from helpers import confirm_all_reviews


def test_golden_checks_evaluate_agent_answer_against_expected_terms() -> None:
    with TestClient(app) as client:
        dataset = client.post("/datasets", json={"name": "Golden", "description": "Expected answers"}).json()
        dataset_id = dataset["id"]
        upload = client.post(
            f"/datasets/{dataset_id}/files",
            files={"files": ("golden.txt", b"Project Delta\nCAPEX 42 USD\nYear 2026", "text/plain")},
        )
        assert upload.status_code == 200
        job = client.post(f"/datasets/{dataset_id}/ingestion-jobs").json()
        _wait_job(client, job["id"])
        confirm_all_reviews(client, dataset_id, "golden_projects")
        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "golden_projects"},
        ).json()
        assert client.post(f"/load-plans/{plan['id']}/confirm").status_code == 200

        created = client.post(
            f"/datasets/{dataset_id}/golden-checks",
            json={"question": "What is the CAPEX for Project Delta?", "expected_terms": ["Delta", "42", "USD"]},
        )
        assert created.status_code == 200
        assert created.json()["expected_terms"] == ["Delta", "42", "USD"]

        result = client.post(f"/datasets/{dataset_id}/golden-checks/run")
        assert result.status_code == 200
        body = result.json()
        assert body["run_id"]
        assert body["total"] == 1
        assert body["snapshot"]["answer_prompt_version"] == "datarules_answer_v2"
        assert body["snapshot"]["embedding_model_id"]
        assert body["snapshot"]["documents"] == 1
        assert body["snapshot"]["golden_checks"] == 1
        assert body["snapshot"]["loaded_plans"] == 1
        assert body["snapshot"]["ready_agent_tables"] == 1
        check = body["checks"][0]
        assert check["last_result"]["status"] == "pass"
        assert check["last_result"]["score"] >= 75
        assert check["last_result"]["missing_terms"] == []

        listed = client.get(f"/datasets/{dataset_id}/golden-checks").json()
        assert listed[0]["last_result"]["status"] == "pass"
        runs = client.get(f"/datasets/{dataset_id}/golden-runs").json()
        assert runs[0]["id"] == body["run_id"]
        assert runs[0]["score"] >= 75
        assert runs[0]["delta"]["previous_run_id"] is None
        assert runs[0]["snapshot"]["answer_prompt_version"] == "datarules_answer_v2"
        gate = client.get(f"/datasets/{dataset_id}/golden-gate").json()
        assert gate["status"] == "passed"
        assert gate["pass"] is True
        assert gate["latest_run"]["id"] == body["run_id"]
        deleted = client.delete(f"/golden-checks/{listed[0]['id']}")
        assert deleted.status_code == 200
        recreated = client.post(
            f"/datasets/{dataset_id}/golden-checks",
            json={"question": "What is the CAPEX for Project Delta?", "expected_terms": ["missing_regression_term"]},
        )
        assert recreated.status_code == 200
        regressed = client.post(f"/datasets/{dataset_id}/golden-checks/run").json()
        assert regressed["delta"]["previous_run_id"] == body["run_id"]
        assert regressed["delta"]["score_delta"] < 0
        assert regressed["delta"]["regressions"][0]["status_regressed"] is True
        failed_gate = client.get(f"/datasets/{dataset_id}/golden-gate").json()
        assert failed_gate["status"] == "failed"
        assert "score_regressed" in failed_gate["reasons"]


def test_golden_checks_export_import_profile_between_datasets() -> None:
    with TestClient(app) as client:
        source = client.post("/datasets", json={"name": "Golden source", "description": "Profile"}).json()
        target = client.post("/datasets", json={"name": "Golden target", "description": "Profile"}).json()
        created = client.post(
            f"/datasets/{source['id']}/golden-checks",
            json={"question": "Where is CAPEX?", "expected_terms": "CAPEX, USD", "notes": "finance smoke"},
        )
        assert created.status_code == 200
        exported = client.get(f"/datasets/{source['id']}/golden-checks/export")
        assert exported.status_code == 200
        profile = exported.json()
        assert profile["profile_version"] == 1
        assert profile["checks"][0]["expected_terms"] == ["CAPEX", "USD"]

        imported = client.post(f"/datasets/{target['id']}/golden-checks/import", json=profile)
        assert imported.status_code == 200
        assert imported.json()["imported"] == 1
        duplicate = client.post(f"/datasets/{target['id']}/golden-checks/import", json=profile)
        assert duplicate.json()["imported"] == 0
        assert duplicate.json()["skipped"][0]["reason"] == "duplicate"
        replaced = client.post(f"/datasets/{target['id']}/golden-checks/import", json={**profile, "replace": True})
        assert replaced.json()["imported"] == 1
        listed = client.get(f"/datasets/{target['id']}/golden-checks").json()
        assert len(listed) == 1
        assert listed[0]["notes"] == "finance smoke"


def test_golden_profile_library_versions_and_applies_to_dataset() -> None:
    with TestClient(app) as client:
        source = client.post("/datasets", json={"name": "Profile source", "description": "Investment projects"}).json()
        target = client.post("/datasets", json={"name": "Profile target", "description": "Investment projects"}).json()
        client.post(
            f"/datasets/{source['id']}/golden-checks",
            json={"question": "What is the investment amount?", "expected_terms": ["amount"], "notes": "core KPI"},
        )
        first = client.post(
            f"/datasets/{source['id']}/golden-profiles",
            json={"name": "Investment projects", "domain": "investment_projects", "description": "Core QA"},
        )
        assert first.status_code == 200
        assert first.json()["version"] == 1
        second = client.post(
            f"/datasets/{source['id']}/golden-profiles",
            json={"name": "Investment projects", "domain": "investment_projects", "description": "Core QA"},
        )
        assert second.json()["version"] == 2

        profiles = client.get("/golden-profiles?domain=investment_projects").json()
        assert profiles[0]["domain"] == "investment_projects"
        applied = client.post(f"/datasets/{target['id']}/golden-profiles/{profiles[0]['id']}/apply", json={"replace": True})
        assert applied.status_code == 200
        assert applied.json()["imported"] == 1
        checks = client.get(f"/datasets/{target['id']}/golden-checks").json()
        assert checks[0]["question"] == "What is the investment amount?"


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/jobs/{job_id}").json()
        if payload["status"] in {"waiting_review", "completed", "failed"}:
            return payload
        sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")
