from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from .db_connection_security import safe_connection_metadata
from .parsers.common import clean_text


def checked_engine(url: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return engine


def database_capabilities(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        extensions = {
            row[0]
            for row in conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_search','pg_trgm')")
            )
        }
    return {
        "vector": "vector" in extensions,
        "bm25": "pg_search" in extensions,
        "trigram": "pg_trgm" in extensions,
        "extensions": sorted(extensions),
    }


def connection_failure_message(exc: Exception, url: str) -> str:
    message = clean_text(str(getattr(exc, "orig", exc)) or exc.__class__.__name__)
    try:
        parsed = make_url(url)
        message = message.replace(parsed.render_as_string(hide_password=False), safe_connection_metadata(url)["display_url"])
        if parsed.password:
            message = message.replace(str(parsed.password), "***")
    except Exception:
        pass
    return message[:500] or exc.__class__.__name__
