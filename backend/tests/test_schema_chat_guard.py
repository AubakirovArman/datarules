from fastapi.testclient import TestClient

from datarules_api.main import app
from datarules_api.schema_chat_guard import sanitize_schema_proposal


def test_schema_chat_sanitizes_fallback_managed_columns() -> None:
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "Schema chat", "description": "Safe"}).json()["id"]
        response = client.post(
            f"/datasets/{dataset_id}/schema-chat",
            json={"message": "Хочу таблицу проектов с суммой и source references", "language": "ru"},
        )
        assert response.status_code == 200
        proposal = response.json()["proposal_json"]
        names = {column["name"] for column in proposal["columns"]}
        assert proposal["table_name"] == "custom_projects"
        assert "Предложена новая таблица" in response.json()["assistant_message"]
        assert "id" not in names
        assert "source_document_id" not in names
        assert proposal["schema_json"]["source_references_required"] is True
        assert proposal["context_usage"]["language"] == "ru"


def test_schema_chat_guard_normalizes_unsafe_llm_like_proposal() -> None:
    proposal = sanitize_schema_proposal(
        {
            "table_name": "2026 Investment Projects!",
            "columns": [
                {"name": "Project Name", "type": "text", "required": True},
                {"name": "source_document_id", "type": "text", "required": True},
                {"name": "Amount USD", "type": "decimal"},
                {"name": "Amount USD", "type": "decimal"},
            ],
        }
    )
    names = [column["name"] for column in proposal["columns"]]
    assert proposal["table_name"] == "t_2026_investment_projects"
    assert names == ["project_name", "amount_usd"]
    assert {item["code"] for item in proposal["identifier_warnings"]} >= {
        "identifier_normalized",
        "managed_column_removed",
        "duplicate_column_removed",
    }
