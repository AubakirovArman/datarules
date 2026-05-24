from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .parsers.common import clean_text


def sql_type(value: str) -> str:
    kind = _kind(value)
    if any(item in kind for item in ("numeric", "decimal", "money")):
        return "numeric"
    if kind in {"integer", "int", "bigint", "smallint", "year"}:
        return "integer"
    if any(item in kind for item in ("float", "double", "real")):
        return "double precision"
    if kind == "date":
        return "date"
    if "timestamp" in kind or kind in {"datetime", "timestamptz"}:
        return "timestamptz"
    if kind in {"boolean", "bool"}:
        return "boolean"
    return "text"


def validate_row_types(row: dict[str, Any], schema_json: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("field_values") if isinstance(row.get("field_values"), dict) else {}
    errors = [
        str(item)
        for item in row.get("validation_errors", [])
        if item and not str(item).startswith(("type_invalid:", "required_missing:", "unknown_field:"))
    ]
    allowed = {str(column.get("name") or "") for column in schema_json.get("target_columns", [])}
    coerced = dict(fields)
    for name in sorted(set(fields) - allowed):
        errors.append(f"unknown_field:{name}")
    for column in schema_json.get("target_columns", []):
        name = str(column.get("name") or "")
        if not name:
            continue
        if column.get("required") and fields.get(name) in (None, ""):
            errors.append(f"required_missing:{name}")
        if name not in fields or fields[name] in (None, ""):
            continue
        value, error = coerce_value(fields[name], str(column.get("type") or "text"))
        if error:
            errors.append(f"type_invalid:{name}:{column.get('type')}")
        else:
            coerced[name] = value
    return {**row, "field_values": coerced, "validation_errors": sorted(set(errors))}


def coerce_value(value: Any, kind: str) -> tuple[Any, str | None]:
    value, error = sql_value(value, kind)
    if error or value is None:
        return value, error
    if isinstance(value, Decimal):
        return str(value), None
    if isinstance(value, date):
        return value.isoformat(), None
    return value, None


def sql_value(value: Any, kind: str) -> tuple[Any, str | None]:
    sql = sql_type(kind)
    if value in (None, ""):
        return None, None
    if sql == "text":
        return clean_text(str(value)), None
    if sql == "numeric":
        return _decimal(value)
    if sql == "integer":
        return _integer(value)
    if sql == "double precision":
        number, error = _decimal(value)
        return (float(number), None) if error is None else (value, error)
    if sql == "date":
        return _date(value)
    if sql == "timestamptz":
        return _datetime(value)
    if sql == "boolean":
        return _bool(value)
    return value, None


def _decimal(value: Any) -> tuple[Any, str | None]:
    text = str(value).strip().replace("\u00a0", " ")
    match = re.search(r"[-+]?\d[\d\s.,]*", text)
    if not match:
        return value, "invalid_numeric"
    raw = _normalize_number(match.group(0))
    try:
        return Decimal(raw), None
    except InvalidOperation:
        return value, "invalid_numeric"


def _integer(value: Any) -> tuple[Any, str | None]:
    number, error = _decimal(value)
    if error:
        return value, error
    if number != number.to_integral_value():
        return value, "invalid_integer"
    return int(number), None


def _date(value: Any) -> tuple[Any, str | None]:
    if isinstance(value, date):
        return value, None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date(), None
        except ValueError:
            pass
    return value, "invalid_date"


def _datetime(value: Any) -> tuple[Any, str | None]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")), None
    except ValueError:
        return value, "invalid_datetime"


def _bool(value: Any) -> tuple[Any, str | None]:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "да", "иә"}:
        return True, None
    if text in {"false", "0", "no", "нет", "жоқ"}:
        return False, None
    return value, "invalid_boolean"


def _kind(value: str) -> str:
    return value.strip().lower().replace(" ", "_").split("(", 1)[0]


def _normalize_number(value: str) -> str:
    raw = value.strip().replace(" ", "")
    comma = raw.rfind(",")
    dot = raw.rfind(".")
    if comma >= 0 and dot >= 0:
        decimal_sep, thousands_sep = (",", ".") if comma > dot else (".", ",")
        return raw.replace(thousands_sep, "").replace(decimal_sep, ".")
    if comma >= 0:
        head, tail = raw.rsplit(",", 1)
        return head + tail if len(tail) == 3 else head + "." + tail
    if dot >= 0:
        head, tail = raw.rsplit(".", 1)
        return head + tail if len(tail) == 3 and len(head) <= 3 else raw
    return raw
