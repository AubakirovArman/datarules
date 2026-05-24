from datetime import datetime
from statistics import mean
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .answering import answer_dataset
from .db import get_db
from .golden_eval import evaluate_golden_answer
from .golden_gate import dataset_golden_gate
from .golden_snapshot import evaluation_snapshot
from .models import Dataset, GoldenCheck, GoldenEvaluationRun, GoldenProfile

router = APIRouter()


@router.get("/datasets/{dataset_id}/golden-checks")
def list_golden_checks(dataset_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _require_dataset(db, dataset_id)
    rows = db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).order_by(GoldenCheck.created_at.desc()).all()
    return [_golden_payload(row) for row in rows]


@router.post("/datasets/{dataset_id}/golden-checks")
def create_golden_check(dataset_id: str, payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_dataset(db, dataset_id)
    try:
        row = _new_golden_check(dataset_id, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(row)
    db.commit()
    db.refresh(row)
    return _golden_payload(row)


@router.get("/datasets/{dataset_id}/golden-checks/export")
def export_golden_checks(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    dataset = _require_dataset(db, dataset_id)
    rows = db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).order_by(GoldenCheck.created_at).all()
    return {"profile_version": 1, "dataset_name": dataset.name, "checks": [_portable_check(row) for row in rows]}


@router.post("/datasets/{dataset_id}/golden-checks/import")
def import_golden_checks(dataset_id: str, payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_dataset(db, dataset_id)
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise HTTPException(400, "Golden profile must contain a checks array")
    if payload.get("replace"):
        db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).delete()
    imported, skipped = _import_golden_items(db, dataset_id, checks, bool(payload.get("replace")))
    db.commit()
    return {"dataset_id": dataset_id, "imported": len(imported), "skipped": skipped, "checks": [_golden_payload(row) for row in imported]}


@router.get("/golden-profiles")
def list_golden_profiles(domain: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = db.query(GoldenProfile)
    if domain:
        query = query.filter(GoldenProfile.domain == domain[:120])
    rows = query.order_by(GoldenProfile.domain, GoldenProfile.name, GoldenProfile.version.desc()).all()
    return [_profile_payload(row) for row in rows]


@router.post("/datasets/{dataset_id}/golden-profiles")
def save_golden_profile(dataset_id: str, payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    dataset = _require_dataset(db, dataset_id)
    rows = db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).order_by(GoldenCheck.created_at).all()
    if not rows:
        raise HTTPException(400, "Create golden checks before saving a profile")
    name = str(payload.get("name") or dataset.name or "Golden profile")
    domain = str(payload.get("domain") or "general")
    profile = GoldenProfile(
        name=name[:200],
        domain=domain.strip()[:120] or "general",
        version=_next_profile_version(db, name, domain),
        description=str(payload.get("description") or "")[:2000],
        checks_json=[_portable_check(row) for row in rows],
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _profile_payload(profile)


@router.post("/datasets/{dataset_id}/golden-profiles/{profile_id}/apply")
def apply_golden_profile(dataset_id: str, profile_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_dataset(db, dataset_id)
    profile = db.get(GoldenProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Golden profile not found")
    replace = bool((payload or {}).get("replace"))
    if replace:
        db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).delete()
    imported, skipped = _import_golden_items(db, dataset_id, profile.checks_json or [], replace)
    db.commit()
    return {"profile": _profile_payload(profile), "imported": len(imported), "skipped": skipped}


@router.post("/datasets/{dataset_id}/golden-checks/run")
def run_golden_checks(dataset_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_dataset(db, dataset_id)
    profile_id = str((payload or {}).get("profile_id") or "") or None
    previous = _previous_run(db, dataset_id, profile_id)
    rows = db.query(GoldenCheck).filter(GoldenCheck.dataset_id == dataset_id).order_by(GoldenCheck.created_at).all()
    results = [_run_golden_check(db, row) for row in rows]
    summary = _run_summary(results)
    delta = _run_delta(results, summary, previous)
    snapshot = evaluation_snapshot(db, dataset_id, len(rows))
    result_json = {"checks": _json_safe(results), "delta": delta, "snapshot": snapshot}
    run = GoldenEvaluationRun(dataset_id=dataset_id, profile_id=profile_id, result_json=result_json, **summary)
    db.add(run)
    db.commit()
    db.refresh(run)
    return {**summary, "dataset_id": dataset_id, "run_id": run.id, "delta": delta, "snapshot": snapshot, "checks": results}


@router.get("/datasets/{dataset_id}/golden-runs")
def list_golden_runs(dataset_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _require_dataset(db, dataset_id)
    rows = db.query(GoldenEvaluationRun).filter(GoldenEvaluationRun.dataset_id == dataset_id).order_by(GoldenEvaluationRun.created_at.desc()).limit(20).all()
    return [_run_payload(row) for row in rows]


@router.get("/datasets/{dataset_id}/golden-gate")
def golden_gate(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_dataset(db, dataset_id)
    return dataset_golden_gate(db, dataset_id)


@router.delete("/golden-checks/{check_id}")
def delete_golden_check(check_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.get(GoldenCheck, check_id)
    if not row:
        raise HTTPException(404, "Golden check not found")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "id": check_id}


def _run_golden_check(db: Session, row: GoldenCheck) -> dict[str, Any]:
    answer = answer_dataset(db, row.dataset_id, row.question, 8)
    row.last_result_json = evaluate_golden_answer(answer, row.expected_terms or [])
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _golden_payload(row)


def _run_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str((row.get("last_result") or {}).get("status") or "blocked") for row in results]
    passed = statuses.count("pass")
    scores = [int((row.get("last_result") or {}).get("score") or 0) for row in results]
    return {"status": "pass" if results and passed == len(results) else "fail", "total": len(results), "passed": passed, "failed": len(results) - passed, "score": round(mean(scores)) if scores else 0}


def _previous_run(db: Session, dataset_id: str, profile_id: str | None) -> GoldenEvaluationRun | None:
    query = db.query(GoldenEvaluationRun).filter(GoldenEvaluationRun.dataset_id == dataset_id)
    query = query.filter(GoldenEvaluationRun.profile_id == profile_id) if profile_id else query.filter(GoldenEvaluationRun.profile_id.is_(None))
    return query.order_by(GoldenEvaluationRun.created_at.desc()).first()


def _run_delta(results: list[dict[str, Any]], summary: dict[str, Any], previous: GoldenEvaluationRun | None) -> dict[str, Any]:
    if not previous:
        return {"previous_run_id": None, "score_delta": None, "regressions": [], "improvements": []}
    previous_checks = _checks_by_question((previous.result_json or {}).get("checks"))
    rows = [_check_delta(row, previous_checks.get(str(row.get("question") or ""))) for row in results]
    regressions = [row for row in rows if row["score_delta"] < 0 or row["status_regressed"]]
    improvements = [row for row in rows if row["score_delta"] > 0 or row["status_improved"]]
    return {
        "previous_run_id": previous.id,
        "previous_score": previous.score,
        "score_delta": int(summary["score"]) - int(previous.score or 0),
        "regressions": regressions[:10],
        "improvements": improvements[:10],
    }


def _checks_by_question(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {str(item.get("question") or ""): item for item in value if isinstance(item, dict)}


def _check_delta(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    now = current.get("last_result") if isinstance(current.get("last_result"), dict) else {}
    before = previous.get("last_result") if previous and isinstance(previous.get("last_result"), dict) else {}
    current_score, previous_score = int(now.get("score") or 0), int(before.get("score") or 0)
    current_status, previous_status = str(now.get("status") or ""), str(before.get("status") or "")
    return {
        "question": str(current.get("question") or ""),
        "previous_score": previous_score,
        "current_score": current_score,
        "score_delta": current_score - previous_score,
        "previous_status": previous_status,
        "current_status": current_status,
        "status_regressed": previous_status == "pass" and current_status != "pass",
        "status_improved": previous_status != "pass" and current_status == "pass",
    }


def _import_golden_items(db: Session, dataset_id: str, checks: list[Any], replace: bool) -> tuple[list[GoldenCheck], list[dict[str, Any]]]:
    imported, skipped = [], []
    existing = set() if replace else _existing_golden_questions(db, dataset_id)
    for item in checks[:100]:
        if not isinstance(item, dict):
            skipped.append({"reason": "invalid_item"})
            continue
        try:
            row = _new_golden_check(dataset_id, item)
        except ValueError as exc:
            skipped.append({"reason": str(exc)})
            continue
        if row.question.strip().lower() in existing:
            skipped.append({"question": row.question, "reason": "duplicate"})
            continue
        existing.add(row.question.strip().lower())
        db.add(row)
        imported.append(row)
    return imported, skipped


def _new_golden_check(dataset_id: str, payload: dict[str, Any]) -> GoldenCheck:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("empty_question")
    return GoldenCheck(dataset_id=dataset_id, question=question[:2000], expected_terms=_expected_terms(payload.get("expected_terms")), notes=str(payload.get("notes") or "")[:2000])


def _expected_terms(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace("\n", ",").split(",")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:20]


def _existing_golden_questions(db: Session, dataset_id: str) -> set[str]:
    rows = db.query(GoldenCheck.question).filter(GoldenCheck.dataset_id == dataset_id).all()
    return {str(row[0]).strip().lower() for row in rows}


def _portable_check(row: GoldenCheck) -> dict[str, Any]:
    return {"question": row.question, "expected_terms": row.expected_terms or [], "notes": row.notes}


def _golden_payload(row: GoldenCheck) -> dict[str, Any]:
    return {"id": row.id, "dataset_id": row.dataset_id, **_portable_check(row), "last_result": row.last_result_json or {}, "created_at": row.created_at, "updated_at": row.updated_at}


def _profile_payload(row: GoldenProfile) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "domain": row.domain, "version": row.version, "description": row.description, "checks": row.checks_json or [], "created_at": row.created_at, "updated_at": row.updated_at}


def _run_payload(row: GoldenEvaluationRun) -> dict[str, Any]:
    result = row.result_json or {}
    return {"id": row.id, "dataset_id": row.dataset_id, "profile_id": row.profile_id, "status": row.status, "total": row.total, "passed": row.passed, "failed": row.failed, "score": row.score, "delta": result.get("delta") or {}, "snapshot": result.get("snapshot") or {}, "result": result, "created_at": row.created_at}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _next_profile_version(db: Session, name: str, domain: str) -> int:
    rows = db.query(GoldenProfile.version).filter(GoldenProfile.name == name[:200], GoldenProfile.domain == domain[:120]).all()
    return max([int(row[0]) for row in rows] or [0]) + 1


def _require_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset
