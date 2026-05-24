from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings
from .connection_urls import connection_url, encrypt_external_url_if_needed, rotate_connection_url_secret_if_needed, set_connection_url
from .db_connection_security import mark_connection_status
from .secret_store import secret_key_status
from .write_policy import write_policy


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from . import models

    _ensure_postgres_extensions()

    if not _run_migrations():
        Base.metadata.create_all(bind=engine)
    _ensure_integrity_indexes()
    _seed_internal_connection(models.DatabaseConnection)
    _encrypt_external_connection_urls(models.DatabaseConnection)
    from .extraction_runs import backfill_missing_extraction_runs
    backfill_missing_extraction_runs()


def _run_migrations() -> bool:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        return False

    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "alembic.ini"
    script_location = project_root / "migrations"
    if not config_path.exists() or not script_location.exists():
        return False

    config = Config(str(config_path))
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
    return True


def _ensure_postgres_extensions() -> None:
    if not settings.database_url.startswith("postgres"):
        return
    with engine.begin() as conn:
        for extension in ("vector", "pg_search", "pg_trgm"):
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))


def _seed_internal_connection(model: type) -> None:
    with SessionLocal() as db:
        existing = db.query(model).filter(model.is_internal.is_(True)).first()
        if existing:
            capabilities = existing.capabilities_json or {}
            existing.capabilities_json = {
                **capabilities,
                "secret_storage": secret_key_status(),
                "write_policy": capabilities.get("write_policy")
                if isinstance(capabilities.get("write_policy"), dict)
                else write_policy(True, ["*"], "Internal DataRules database."),
            }
            existing.capabilities_json = mark_connection_status(
                existing.capabilities_json,
                connection_url(existing),
                "ok",
                "Internal connection available.",
            )
            db.commit()
            return
        capabilities = {
            "vector": True,
            "bm25": settings.keyword_search_engine == "pg_search",
            "trigram": True,
            "embedding_model": settings.embedding_model_id,
            "embedding_dimensions": settings.embedding_dimensions,
            "secret_storage": secret_key_status(),
            "write_policy": write_policy(True, ["*"], "Internal DataRules database."),
        }
        connection = model(
            name="DataRules PostgreSQL",
            description="Internal PostgreSQL for DataRules datasets, agent tables, BM25, and vectors.",
            default_schema=settings.default_db_schema,
            is_internal=True,
            capabilities_json=mark_connection_status(
                capabilities,
                settings.database_url,
                "ok",
                "Internal connection available.",
            ),
        )
        set_connection_url(connection, settings.database_url, encrypt=False)
        db.add(connection)
        db.commit()


def _encrypt_external_connection_urls(model: type) -> None:
    with SessionLocal() as db:
        changed = False
        for connection in db.query(model).filter(model.is_internal.is_(False)).all():
            try:
                changed = rotate_connection_url_secret_if_needed(connection) or changed
                changed = encrypt_external_url_if_needed(connection) or changed
                connection.capabilities_json = {
                    **(connection.capabilities_json or {}),
                    "secret_storage": secret_key_status(),
                }
            except ValueError as exc:
                changed = True
                connection.capabilities_json = _mark_secret_invalid(connection.capabilities_json or {}, str(exc))
        if changed:
            db.commit()


def _mark_secret_invalid(capabilities: dict, message: str) -> dict:
    connection = dict(capabilities.get("connection") or {})
    connection.update({"last_status": "secret_invalid", "last_message": message})
    return {**capabilities, "secret_storage": secret_key_status(), "connection": connection}


def _ensure_integrity_indexes() -> None:
    if not settings.database_url.startswith("postgres"):
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM document_ai_summaries
                WHERE id IN (
                  SELECT id FROM (
                    SELECT id,
                           row_number() OVER (
                             PARTITION BY document_id
                             ORDER BY updated_at DESC, created_at DESC, id DESC
                           ) AS row_number
                    FROM document_ai_summaries
                  ) ranked
                  WHERE row_number > 1
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_document_ai_summaries_document
                ON document_ai_summaries(document_id)
                """
            )
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
