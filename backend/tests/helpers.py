from fastapi.testclient import TestClient

from datarules_api.db import SessionLocal
from datarules_api.models import SchemaProposal


def confirm_all_reviews(client: TestClient, dataset_id: str, table: str) -> None:
    reviews = client.get(f"/datasets/{dataset_id}/document-reviews")
    assert reviews.status_code == 200
    for review in reviews.json():
        if review["status"] == "confirmed":
            continue
        response = client.post(
            f"/document-reviews/{review['id']}/decision",
            json={
                "selected_doc_type": review["doc_type_options"][0]["value"],
                "selected_table": table,
                "notes": "Test route confirmation",
            },
        )
        assert response.status_code == 200
    approve_test_schema(client, dataset_id, table)


def approve_test_schema(client: TestClient, dataset_id: str, table: str) -> None:
    with SessionLocal() as db:
        proposal = SchemaProposal(
            dataset_id=dataset_id,
            proposal_json={
                "dataset_summary": f"Test schema for {table}",
                "tables": [{"name": table, "columns": [{"name": "title", "type": "text"}]}],
            },
        )
        db.add(proposal)
        db.commit()
        proposal_id = proposal.id
    approved = client.post(f"/schema-proposals/{proposal_id}/approve")
    assert approved.status_code == 200
