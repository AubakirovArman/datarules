from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DatabaseConnection


def write_policy(enabled: bool, schemas: list[str] | None = None, reason: str = "") -> dict[str, Any]:
    return {"enabled": enabled, "schemas": schemas or [], "reason": reason}


def connection_can_write(connection: "DatabaseConnection | None", schema: str) -> bool:
    if not connection:
        return False
    if connection.is_internal:
        return True
    policy = (connection.capabilities_json or {}).get("write_policy")
    if not isinstance(policy, dict) or not policy.get("enabled"):
        return False
    schemas = [str(item) for item in policy.get("schemas", [])]
    return "*" in schemas or schema in schemas


def write_denial(connection: "DatabaseConnection | None", schema: str) -> dict[str, Any]:
    name = connection.name if connection else "not configured"
    return {
        "severity": "error",
        "code": "write_not_allowed",
        "connection": name,
        "schema": schema,
        "message": f"Write access is not enabled for {name} schema {schema}.",
    }
