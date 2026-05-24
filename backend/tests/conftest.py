import os
from pathlib import Path

import psycopg
from psycopg import sql


TEST_DB = os.environ.get("DATARULES_TEST_DB", "datarules_test")
TEST_ROOT = Path(__file__).resolve().parents[2] / "storage" / "test"


def _admin_url() -> str:
    return os.environ.get(
        "DATARULES_TEST_ADMIN_URL",
        "postgresql://datarules:datarules@127.0.0.1:55433/postgres",
    )


def _database_url() -> str:
    return os.environ.get(
        "DATARULES_TEST_DATABASE_URL",
        f"postgresql+psycopg://datarules:datarules@127.0.0.1:55433/{TEST_DB}",
    )


def _plain_database_url() -> str:
    return _database_url().replace("postgresql+psycopg://", "postgresql://", 1)


def _ensure_database() -> None:
    with psycopg.connect(_admin_url(), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [TEST_DB]).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))


def _reset_database() -> None:
    with psycopg.connect(_plain_database_url(), autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


_ensure_database()
_reset_database()
os.environ["DATABASE_URL"] = _database_url()
os.environ["RAW_STORAGE_DIR"] = str(TEST_ROOT / "raw")
os.environ["CANONICAL_STORAGE_DIR"] = str(TEST_ROOT / "canonical")
os.environ["PAGE_IMAGE_DIR"] = str(TEST_ROOT / "page_images")
os.environ["ENABLE_GEMMA_CALLS"] = "false"
os.environ["ENABLE_EMBEDDING_CALLS"] = "false"


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    _ = (session, exitstatus)
    _reset_database()
