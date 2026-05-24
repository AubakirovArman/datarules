from typing import Any

from .secret_store import decrypt_secret, encrypt_secret, rotate_legacy_secret

SENTINEL = "encrypted://datarules-connection-url"


def connection_url(connection: Any) -> str:
    encrypted = getattr(connection, "sqlalchemy_url_encrypted", None)
    if encrypted:
        return decrypt_secret(str(encrypted))
    return connection.sqlalchemy_url


def set_connection_url(connection: Any, url: str, encrypt: bool) -> None:
    if encrypt:
        connection.sqlalchemy_url = SENTINEL
        connection.sqlalchemy_url_encrypted = encrypt_secret(url)
    else:
        connection.sqlalchemy_url = url
        connection.sqlalchemy_url_encrypted = None


def encrypt_external_url_if_needed(connection: Any) -> bool:
    if connection.is_internal or getattr(connection, "sqlalchemy_url_encrypted", None):
        return False
    if not connection.sqlalchemy_url or connection.sqlalchemy_url == SENTINEL:
        return False
    set_connection_url(connection, connection.sqlalchemy_url, encrypt=True)
    return True


def rotate_connection_url_secret_if_needed(connection: Any) -> bool:
    encrypted = getattr(connection, "sqlalchemy_url_encrypted", None)
    if connection.is_internal or not encrypted:
        return False
    rotated, changed = rotate_legacy_secret(str(encrypted))
    if changed:
        connection.sqlalchemy_url_encrypted = rotated
        connection.sqlalchemy_url = SENTINEL
    return changed
