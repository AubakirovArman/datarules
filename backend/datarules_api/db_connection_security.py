from datetime import datetime
from ipaddress import ip_address
from typing import Any

from sqlalchemy.engine import URL, make_url

from .parsers.common import clean_text


def safe_connection_metadata(url: str) -> dict[str, Any]:
    parsed = make_url(url)
    host = parsed.host or ""
    return {
        "display_url": _masked_url(parsed),
        "driver": parsed.drivername,
        "username": parsed.username or "",
        "host": host,
        "port": parsed.port,
        "database": parsed.database or "",
        "network_zone": _network_zone(host),
    }


def mark_connection_status(
    capabilities: dict[str, Any],
    url: str,
    status: str,
    message: str = "",
) -> dict[str, Any]:
    return {
        **capabilities,
        "connection": {
            **safe_connection_metadata(url),
            "last_status": status,
            "last_message": clean_text(message)[:500],
            "last_checked_at": datetime.utcnow().isoformat(),
        },
    }


def _masked_url(url: URL) -> str:
    masked = url.set(password="***") if url.password else url
    return masked.render_as_string(hide_password=False).replace("%2A%2A%2A", "***")


def _network_zone(host: str) -> str:
    value = host.strip().lower()
    if not value:
        return "unknown"
    if value in {"localhost", "host.docker.internal"}:
        return "local"
    try:
        ip = ip_address(value)
    except ValueError:
        return "hostname"
    if ip.is_loopback:
        return "local"
    if ip.is_private:
        return "private"
    return "public"
