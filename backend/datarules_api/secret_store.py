import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

PREFIX = "fernet:"
DEV_SEED = b"datarules-local-development-secret-v1"


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value.removeprefix(PREFIX).encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Encrypted secret cannot be decrypted with the configured key.") from exc


def rotate_legacy_secret(value: str) -> tuple[str, bool]:
    if not value or not value.startswith(PREFIX) or not _configured_key():
        return value, False
    try:
        _fernet().decrypt(value.removeprefix(PREFIX).encode())
        return value, False
    except InvalidToken:
        try:
            plaintext = _dev_fernet().decrypt(value.removeprefix(PREFIX).encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Encrypted secret cannot be decrypted with the configured key or legacy fallback.") from exc
    return PREFIX + _fernet().encrypt(plaintext.encode()).decode(), True


def secret_key_status() -> str:
    return "configured" if _configured_key() else "development_fallback"


def _fernet() -> Fernet:
    return Fernet(_key())


def _key() -> bytes:
    configured = _configured_key()
    if configured:
        return configured.encode()
    return _dev_key()


def _dev_fernet() -> Fernet:
    return Fernet(_dev_key())


def _dev_key() -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(DEV_SEED).digest())


def _configured_key() -> str:
    return get_settings().datarules_secret_key.strip()
