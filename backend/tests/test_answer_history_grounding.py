from fastapi.testclient import TestClient

from datarules_api.main import app
from datarules_api.schemas import AskResponse
from datarules_api import ask_routes


def test_answer_history_persists_grounding(monkeypatch) -> None:
    def fake_answer(*_: object, **__: object) -> AskResponse:
        return AskResponse(
            answer="Grounded answer [1].",
            confidence="medium",
            citations=[],
            grounding={"status": "grounded", "valid_markers": ["[1]"], "coverage": 1.0},
            retrieval_mode="hybrid_search",
            model_source="test",
            prompt_version="test_v1",
            model_id="test-model",
        )

    monkeypatch.setattr(ask_routes, "answer_dataset", fake_answer)
    with TestClient(app) as client:
        dataset_id = client.post("/datasets", json={"name": "History grounding", "description": "Audit"}).json()["id"]
        response = client.post(f"/datasets/{dataset_id}/ask", json={"query": "Q", "limit": 1})
        history = client.get(f"/datasets/{dataset_id}/answers").json()

    assert response.status_code == 200
    assert history[0]["grounding_json"]["status"] == "grounded"
    assert history[0]["grounding_json"]["coverage"] == 1.0
