from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .answering import answer_dataset
from .db import get_db
from .golden_routes import router as golden_router
from .models import AgentAnswer, Dataset
from .schemas import AgentAnswerOut, AskRequest, AskResponse

router = APIRouter()
router.include_router(golden_router)


@router.post("/datasets/{dataset_id}/ask", response_model=AskResponse)
def ask_dataset(dataset_id: str, payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    _require_dataset(db, dataset_id)
    query = payload.query.strip()
    if not query:
        raise HTTPException(400, "Question is empty")
    limit = max(1, min(payload.limit, 12))
    answer = answer_dataset(db, dataset_id, query, limit)
    row = _record_answer(db, dataset_id, query, answer)
    return answer.model_copy(update={"answer_id": row.id})


@router.post("/agent-answers/{answer_id}/replay", response_model=AskResponse)
def replay_answer(answer_id: str, db: Session = Depends(get_db)) -> AskResponse:
    original = db.get(AgentAnswer, answer_id)
    if not original:
        raise HTTPException(404, "Answer not found")
    answer = answer_dataset(db, original.dataset_id, original.query, 8)
    row = _record_answer(db, original.dataset_id, original.query, answer, original.id)
    return answer.model_copy(update={"answer_id": row.id, "replay_of_answer_id": original.id})


def _record_answer(
    db: Session,
    dataset_id: str,
    query: str,
    answer: AskResponse,
    replay_of: str | None = None,
) -> AgentAnswer:
    row = AgentAnswer(
        dataset_id=dataset_id,
        query=query,
        answer=answer.answer,
        confidence=answer.confidence,
        retrieval_mode=answer.retrieval_mode,
        model_source=answer.model_source,
        prompt_version=answer.prompt_version,
        model_id=answer.model_id,
        replay_of_answer_id=replay_of,
        citations_json=[item.model_dump() for item in answer.citations],
        grounding_json=answer.grounding,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/datasets/{dataset_id}/answers", response_model=list[AgentAnswerOut])
def list_answers(dataset_id: str, db: Session = Depends(get_db)) -> list[AgentAnswer]:
    _require_dataset(db, dataset_id)
    return (
        db.query(AgentAnswer)
        .filter(AgentAnswer.dataset_id == dataset_id)
        .order_by(AgentAnswer.created_at.desc())
        .limit(50)
        .all()
    )


def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset
