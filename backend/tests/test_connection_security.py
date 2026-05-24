from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from types import SimpleNamespace

from datarules_api.config import get_settings
from datarules_api.connection_urls import SENTINEL, connection_url, rotate_connection_url_secret_if_needed, set_connection_url
from datarules_api.db import SessionLocal
from datarules_api.main import app
from datarules_api.models import DatabaseConnection
from datarules_api.secret_store import encrypt_secret


def test_connection_response_masks_url_and_records_status() -> None:
    with TestClient(app) as client:
        bad_default_schema = client.post(
            "/database-connections",
            json={
                "name": "Bad default schema",
                "description": "unsafe schema",
                "sqlalchemy_url": get_settings().database_url,
                "default_schema": "Bad Schema",
            },
        )
        assert bad_default_schema.status_code == 400

        created = client.post(
            "/database-connections",
            json={
                "name": "Masked connection",
                "description": "password must not leak",
                "sqlalchemy_url": get_settings().database_url,
                "default_schema": "public",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert "sqlalchemy_url" not in body
        connection = body["capabilities_json"]["connection"]
        assert connection["last_status"] == "ok"
        assert connection["display_url"]
        assert "datarules:datarules" not in connection["display_url"]
        assert "***" in connection["display_url"]
        with SessionLocal() as db:
            stored = db.get(DatabaseConnection, body["id"])
            assert stored is not None
            assert stored.sqlalchemy_url != get_settings().database_url
            assert "datarules:datarules" not in stored.sqlalchemy_url
            assert stored.sqlalchemy_url_encrypted
            assert "datarules:datarules" not in stored.sqlalchemy_url_encrypted
            assert connection_url(stored) == get_settings().database_url

        tested = client.post(f"/database-connections/{body['id']}/test")
        assert tested.status_code == 200
        assert tested.json()["capabilities"]["connection"]["last_status"] == "ok"

        listed = client.get("/database-connections")
        payload = next(item for item in listed.json() if item["id"] == body["id"])
        assert "sqlalchemy_url" not in payload
        assert payload["capabilities_json"]["connection"]["display_url"] == connection["display_url"]

        system_schema = client.patch(
            f"/database-connections/{body['id']}/write-policy",
            json={"enabled": True, "schemas": ["pg_catalog"], "confirm_external_write": True},
        )
        assert system_schema.status_code == 400
        unsafe_schema = client.patch(
            f"/database-connections/{body['id']}/write-policy",
            json={"enabled": True, "schemas": ["Bad Schema"], "confirm_external_write": True},
        )
        assert unsafe_schema.status_code == 400

        with SessionLocal() as db:
            stored = db.get(DatabaseConnection, body["id"])
            assert stored is not None
            stored.sqlalchemy_url_encrypted = "fernet:not-a-token"
            db.commit()
        invalid = client.post(f"/database-connections/{body['id']}/test")
        assert invalid.status_code == 400


def test_unreachable_connection_returns_managed_failure_status() -> None:
    bad_url = "postgresql+psycopg://bad:secret@127.0.0.1:1/missing"
    with TestClient(app) as client:
        failed_create = client.post(
            "/database-connections",
            json={
                "name": "Offline connection",
                "description": "should fail cleanly",
                "sqlalchemy_url": bad_url,
                "default_schema": "public",
            },
        )
        assert failed_create.status_code == 400
        assert failed_create.json()["detail"]["code"] == "connection_failed"
        assert "secret" not in failed_create.json()["detail"]["message"]

        created = client.post(
            "/database-connections",
            json={
                "name": "Will break",
                "description": "persist failed status",
                "sqlalchemy_url": get_settings().database_url,
                "default_schema": "public",
            },
        ).json()
        with SessionLocal() as db:
            stored = db.get(DatabaseConnection, created["id"])
            assert stored is not None
            set_connection_url(stored, bad_url, encrypt=True)
            db.commit()

        failed_test = client.post(f"/database-connections/{created['id']}/test")
        assert failed_test.status_code == 400
        listed = client.get("/database-connections").json()
        status = next(item for item in listed if item["id"] == created["id"])["capabilities_json"]["connection"]
        assert status["last_status"] == "failed"
        assert "***" in status["display_url"]


def test_legacy_fallback_secret_rotates_to_configured_key(monkeypatch) -> None:
    url = "postgresql+psycopg://user:pass@127.0.0.1:55433/db"
    monkeypatch.delenv("DATARULES_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    legacy = encrypt_secret(url)

    monkeypatch.setenv("DATARULES_SECRET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    connection = SimpleNamespace(is_internal=False, sqlalchemy_url=SENTINEL, sqlalchemy_url_encrypted=legacy)

    assert rotate_connection_url_secret_if_needed(connection) is True
    assert connection.sqlalchemy_url_encrypted != legacy
    assert connection_url(connection) == url

    monkeypatch.delenv("DATARULES_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    try:
        connection_url(connection)
    except ValueError as exc:
        assert "configured key" in str(exc)
    else:
        raise AssertionError("rotated secret should not decrypt with the legacy fallback")
    finally:
        get_settings.cache_clear()
