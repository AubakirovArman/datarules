from typing import Any

from fastapi import HTTPException

from .db_identifiers import IDENTIFIER_RE
from .models import DatabaseConnection

SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "paradedb", "pdb", "tiger", "topology"}


def requested_schemas(value: Any, default: str) -> list[str]:
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = [default]
    schemas = [str(item).strip() for item in raw if str(item).strip()]
    return schemas or [default]


def validate_write_policy_request(
    connection: DatabaseConnection,
    enabled: bool,
    schemas: list[str],
    payload: dict[str, Any],
) -> None:
    if connection.is_internal or not enabled:
        return
    if "*" in schemas:
        raise HTTPException(400, "External write policy must name explicit schemas; wildcard is not allowed.")
    blocked = sorted({schema for schema in schemas if _unsafe_schema(schema)})
    if blocked:
        raise HTTPException(400, f"External write policy cannot target unsafe schemas: {', '.join(blocked)}")
    if not payload.get("confirm_external_write"):
        raise HTTPException(400, "confirm_external_write is required before enabling writes to an external database.")


def validate_connection_default_schema(schema: str) -> None:
    if _unsafe_schema(schema):
        raise HTTPException(400, "default_schema must be a safe user schema identifier.")


def _unsafe_schema(schema: str) -> bool:
    value = str(schema or "").strip()
    return not IDENTIFIER_RE.fullmatch(value) or value.startswith("pg_") or value in SYSTEM_SCHEMAS
