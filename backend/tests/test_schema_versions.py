from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import SchemaProposal


def test_approving_schema_proposal_creates_active_schema_version() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Versions", "description": "Schemas"}).json()["id"]
        first_id = _proposal(dataset_id, "first_projects")
        second_id = _proposal(dataset_id, "second_projects")

        first = client.post(f"/schema-proposals/{first_id}/approve")
        assert first.status_code == 200
        versions = client.get(f"/datasets/{dataset_id}/schema-versions").json()
        assert len(versions) == 1
        assert versions[0]["version"] == 1
        assert versions[0]["status"] == "active"
        assert versions[0]["proposal_id"] == first_id
        assert versions[0]["schema_json"]["tables"][0]["name"] == "first_projects"

        again = client.post(f"/schema-proposals/{first_id}/approve")
        assert again.status_code == 200
        assert len(client.get(f"/datasets/{dataset_id}/schema-versions").json()) == 1

        second = client.post(f"/schema-proposals/{second_id}/approve")
        assert second.status_code == 200
        versions = client.get(f"/datasets/{dataset_id}/schema-versions").json()
        assert [row["version"] for row in versions] == [2, 1]
        assert versions[0]["status"] == "active"
        assert versions[1]["status"] == "archived"


def test_load_plan_can_use_approved_schema_version() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Version load", "description": "Use schema"}).json()["id"]
        proposal_id = _proposal(dataset_id, "versioned_projects")
        approved = client.post(f"/schema-proposals/{proposal_id}/approve")
        assert approved.status_code == 200
        version = client.get(f"/datasets/{dataset_id}/schema-versions").json()[0]

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={
                "target_mode": "new",
                "target_table": "versioned_projects",
                "schema_version_id": version["id"],
            },
        )
        assert plan.status_code == 200
        body = plan.json()
        assert body["schema_version_id"] == version["id"]
        assert body["schema_json"]["schema_version"]["id"] == version["id"]
        assert body["schema_json"]["target_columns"] == [{"name": "title", "type": "text", "required": False}]


def test_new_table_load_is_blocked_when_schema_proposal_is_not_approved() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Schema gate", "description": "Approval"}).json()["id"]
        _proposal(dataset_id, "gated_projects")

        plan = client.post(
            f"/datasets/{dataset_id}/load-plans",
            json={"target_mode": "new", "target_table": "gated_projects"},
        )
        assert plan.status_code == 200
        body = plan.json()
        assert body["status"] == "blocked"
        assert any(issue["code"] == "schema_not_approved" for issue in body["validation_issues"])


def _proposal(dataset_id: str, table_name: str) -> str:
    with SessionLocal() as db:
        proposal = SchemaProposal(
            dataset_id=dataset_id,
            proposal_json={
                "dataset_summary": f"Schema for {table_name}",
                "tables": [{"name": table_name, "columns": [{"name": "title", "type": "text"}]}],
            },
        )
        db.add(proposal)
        db.commit()
        proposal_id = proposal.id
    return proposal_id
