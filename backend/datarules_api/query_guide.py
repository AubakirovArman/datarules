from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .db import get_db
from .models import Dataset, Document, LoadPlan, SchemaVersion

router = APIRouter()


@router.get("/datasets/{dataset_id}/query-guide")
def query_guide(
    dataset_id: str,
    language: str = Query("ru", pattern="^(ru|kk|en)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    plans = (
        db.query(LoadPlan)
        .filter(LoadPlan.dataset_id == dataset_id)
        .order_by(LoadPlan.updated_at.desc(), LoadPlan.created_at.desc())
        .all()
    )
    versions = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.dataset_id == dataset_id)
        .order_by(SchemaVersion.version.desc())
        .all()
    )
    doc_count = db.query(Document.id).filter(Document.dataset_id == dataset_id).count()
    tables = _tables(plans, versions)
    modes = _modes(plans, doc_count)
    fields = _fields(tables)
    filters = _filters(fields, tables)
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "language": language,
        "status": _status(modes, tables, doc_count),
        "tables": tables,
        "fields": fields,
        "filters": filters,
        "search_modes": modes,
        "examples": _examples(language, tables, fields, modes),
        "guardrails": _guardrails(language),
        "next_actions": _next_actions(tables, modes, doc_count),
    }


def _tables(plans: list[LoadPlan], versions: list[SchemaVersion]) -> list[dict[str, Any]]:
    rows = [_plan_table(plan) for plan in plans if plan.status == "loaded"]
    known = {row["table"] for row in rows}
    for plan in plans:
        if plan.status == "loaded" or plan.target_table in known:
            continue
        rows.append(_plan_table(plan))
        known.add(plan.target_table)
    for version in versions:
        for table in _version_tables(version):
            if table["table"] in known:
                continue
            rows.append(table)
            known.add(table["table"])
    return rows[:20]


def _plan_table(plan: LoadPlan) -> dict[str, Any]:
    agent = plan.agent_preparation_json or {}
    return {
        "plan_id": plan.id,
        "schema_version_id": plan.schema_version_id,
        "schema": plan.schema_name,
        "table": plan.target_table,
        "status": plan.status,
        "rows": len(plan.preview_rows or []),
        "loaded_rows": int(agent.get("inserted_records") or 0),
        "chunk_table": agent.get("chunk_table"),
        "ready_for_agent": bool(agent.get("ready_for_agent")),
        "keyword_search": bool(agent.get("keyword_search") or agent.get("bm25")),
        "semantic_search": bool(agent.get("semantic_search")),
        "bm25": bool(agent.get("bm25")),
        "fields": _columns(plan.schema_json or {}),
    }


def _version_tables(version: SchemaVersion) -> list[dict[str, Any]]:
    schema = version.schema_json or {}
    tables = schema.get("tables") if isinstance(schema.get("tables"), list) else []
    rows = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        name = str(table.get("name") or table.get("table_name") or "")
        if not name:
            continue
        rows.append({
            "schema_version_id": version.id,
            "schema": "public",
            "table": name,
            "status": f"schema_{version.status}",
            "rows": 0,
            "loaded_rows": 0,
            "ready_for_agent": False,
            "keyword_search": False,
            "semantic_search": False,
            "bm25": False,
            "fields": _columns({"target_columns": table.get("columns", [])}),
        })
    return rows


def _columns(schema: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for column in schema.get("target_columns", []) if isinstance(schema, dict) else []:
        if isinstance(column, dict) and column.get("name"):
            rows.append({"name": str(column["name"]), "type": str(column.get("type") or "text")})
    return rows[:40]


def _fields(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for table in tables:
        for field in table.get("fields", []):
            name = str(field.get("name") or "")
            if not name:
                continue
            seen.setdefault(name, {"name": name, "type": field.get("type", "text"), "tables": []})
            seen[name]["tables"].append(table["table"])
    return list(seen.values())[:80]


def _filters(fields: list[dict[str, Any]], tables: list[dict[str, Any]]) -> list[dict[str, str]]:
    names = {str(field["name"]) for field in fields}
    preferred = ["year", "quarter", "company_name", "project_name", "region", "status", "currency", "amount"]
    rows = [{"name": name, "source": "structured_field"} for name in preferred if name in names]
    rows.extend([{"name": "source_file", "source": "source_reference"}, {"name": "page", "source": "source_reference"}])
    if any(table.get("ready_for_agent") for table in tables):
        rows.append({"name": "target_table", "source": "agent_chunk"})
    return rows


def _modes(plans: list[LoadPlan], doc_count: int) -> list[dict[str, Any]]:
    loaded = [plan for plan in plans if plan.status == "loaded"]
    semantic = any((plan.agent_preparation_json or {}).get("semantic_search") for plan in loaded)
    keyword = any((plan.agent_preparation_json or {}).get("keyword_search") or (plan.agent_preparation_json or {}).get("bm25") for plan in loaded)
    modes = [{"mode": "raw_keyword", "ready": doc_count > 0, "scope": "document_blocks"}]
    modes.append({"mode": "sql", "ready": bool(loaded), "scope": "loaded_tables"})
    modes.append({"mode": "keyword", "ready": keyword, "scope": "agent_chunks"})
    modes.append({"mode": "semantic", "ready": semantic, "scope": "agent_chunks"})
    modes.append({"mode": "hybrid", "ready": keyword or semantic, "scope": "agent_chunks_and_raw_blocks"})
    return modes


def _status(modes: list[dict[str, Any]], tables: list[dict[str, Any]], doc_count: int) -> str:
    if not doc_count:
        return "upload_documents"
    if any(mode["mode"] == "hybrid" and mode["ready"] for mode in modes):
        return "ready_for_agent"
    if any(table["status"] == "loaded" for table in tables):
        return "loaded_without_search"
    if tables:
        return "schema_ready"
    return "analysis_ready"


def _examples(lang: str, tables: list[dict[str, Any]], fields: list[dict[str, Any]], modes: list[dict[str, Any]]) -> list[dict[str, str]]:
    table = tables[0]["table"] if tables else "documents"
    field_names = {field["name"] for field in fields}
    amount_filter = "amount" if "amount" in field_names else "confidence"
    examples = {
        "ru": [
            ("sql", f"Покажи строки из {table}, где {amount_filter} больше заданного значения."),
            ("keyword", "Где в документах упоминается CAPEX или номер договора?"),
            ("semantic", "Найди проекты по энергетике, даже если формулировка отличается."),
            ("hybrid", "Какие документы подтверждают сумму и статус проекта?"),
        ],
        "kk": [
            ("sql", f"{table} кестесінен {amount_filter} бойынша сүзілген жолдарды көрсет."),
            ("keyword", "Құжаттарда CAPEX немесе шарт нөмірі қай жерде кездеседі?"),
            ("semantic", "Энергетика жобаларын мағынасы бойынша тап."),
            ("hybrid", "Жоба сомасы мен мәртебесін қандай құжаттар растайды?"),
        ],
        "en": [
            ("sql", f"Show rows from {table} filtered by {amount_filter}."),
            ("keyword", "Where do documents mention CAPEX or a contract number?"),
            ("semantic", "Find energy projects even if the wording is different."),
            ("hybrid", "Which documents support the project amount and status?"),
        ],
    }
    ready = {mode["mode"] for mode in modes if mode["ready"]}
    return [{"mode": mode, "question": text} for mode, text in examples[lang] if mode in ready or mode == "sql"]


def _guardrails(lang: str) -> list[str]:
    rows = {
        "ru": [
            "Для точных чисел и фильтров используйте SQL/табличный preview.",
            "Для названий, кодов и договоров используйте keyword/BM25.",
            "Для смысловых вопросов используйте semantic/hybrid и проверяйте citations.",
        ],
        "kk": [
            "Нақты сандар мен сүзгілер үшін SQL/кесте preview қолданыңыз.",
            "Атаулар, кодтар және шарттар үшін keyword/BM25 қолданыңыз.",
            "Мағыналық сұрақтар үшін semantic/hybrid қолданып, citations тексеріңіз.",
        ],
        "en": [
            "Use SQL/table preview for exact numbers and filters.",
            "Use keyword/BM25 for names, codes, and contracts.",
            "Use semantic/hybrid for meaning-based questions and check citations.",
        ],
    }
    return rows[lang]


def _next_actions(tables: list[dict[str, Any]], modes: list[dict[str, Any]], doc_count: int) -> list[str]:
    if not doc_count:
        return ["readiness_next_upload"]
    if not tables:
        return ["readiness_next_summary", "readiness_next_routing", "readiness_next_schema"]
    if not any(table["status"] == "loaded" for table in tables):
        return ["readiness_next_preview", "readiness_next_materialization"]
    if not any(mode["mode"] == "hybrid" and mode["ready"] for mode in modes):
        return ["readiness_next_retrieval"]
    return []
