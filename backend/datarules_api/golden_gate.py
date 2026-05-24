from typing import Any

from sqlalchemy.orm import Session

from .config import get_settings
from .models import GoldenCheck, GoldenEvaluationRun


def dataset_golden_gate(db: Session, dataset_id: str) -> dict[str, Any]:
    settings = get_settings()
    checks = db.query(GoldenCheck.id).filter(GoldenCheck.dataset_id == dataset_id).count()
    latest = _latest_run(db, dataset_id)
    thresholds = {
        "min_score": settings.golden_min_score,
        "allowed_score_drop": settings.golden_allowed_score_drop,
        "fail_on_regression": settings.golden_fail_on_regression,
    }
    if not checks:
        return _payload("pending", ["golden_checks_missing"], thresholds, checks, latest)
    if not latest:
        return _payload("pending", ["golden_run_missing"], thresholds, checks, latest)
    reasons = _failure_reasons(latest, thresholds)
    return _payload("failed" if reasons else "passed", reasons, thresholds, checks, latest)


def _latest_run(db: Session, dataset_id: str) -> GoldenEvaluationRun | None:
    return (
        db.query(GoldenEvaluationRun)
        .filter(GoldenEvaluationRun.dataset_id == dataset_id)
        .order_by(GoldenEvaluationRun.created_at.desc())
        .first()
    )


def _failure_reasons(row: GoldenEvaluationRun, thresholds: dict[str, Any]) -> list[str]:
    result = row.result_json or {}
    delta = result.get("delta") if isinstance(result.get("delta"), dict) else {}
    snapshot = result.get("snapshot") if isinstance(result.get("snapshot"), dict) else {}
    reasons = []
    if row.status != "pass":
        reasons.append("golden_run_failed")
    if int(row.score or 0) < int(thresholds["min_score"]):
        reasons.append("score_below_threshold")
    score_delta = delta.get("score_delta")
    allowed = int(thresholds["allowed_score_drop"])
    if isinstance(score_delta, int | float) and score_delta < -allowed:
        reasons.append("score_regressed")
    if thresholds["fail_on_regression"] and delta.get("regressions"):
        reasons.append("check_regressions")
    if snapshot and int(snapshot.get("ready_agent_tables") or 0) < 1:
        reasons.append("agent_tables_missing")
    return reasons


def _payload(
    status: str,
    reasons: list[str],
    thresholds: dict[str, Any],
    checks: int,
    latest: GoldenEvaluationRun | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "pass": status == "passed",
        "reasons": reasons,
        "thresholds": thresholds,
        "checks": checks,
        "latest_run": _run_payload(latest),
    }


def _run_payload(row: GoldenEvaluationRun | None) -> dict[str, Any] | None:
    if not row:
        return None
    result = row.result_json or {}
    return {
        "id": row.id,
        "status": row.status,
        "score": row.score,
        "passed": row.passed,
        "total": row.total,
        "delta": result.get("delta") or {},
        "snapshot": result.get("snapshot") or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
