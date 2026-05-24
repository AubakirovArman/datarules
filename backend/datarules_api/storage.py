from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from .config import get_settings

ALLOWED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".json",
    ".md",
    ".markdown",
    ".pdf",
    ".ppt",
    ".pptx",
    ".txt",
    ".xls",
    ".xlsm",
    ".xlsx",
    ".xml",
}


class UploadPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def save_upload(dataset_id: str, upload: UploadFile) -> tuple[Path, str]:
    settings = get_settings()
    target_dir = settings.raw_storage_dir / dataset_id
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload.filename or "upload.bin").suffix
    _validate_file_type(upload, suffix)
    path = target_dir / f"{uuid4().hex}{suffix}"
    digest = sha256()
    total = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024

    with path.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                out.close()
                path.unlink(missing_ok=True)
                raise UploadPolicyError("file_too_large", f"File exceeds {settings.max_upload_mb} MB limit.")
            digest.update(chunk)
            out.write(chunk)

    await upload.seek(0)
    return path, digest.hexdigest()


def _validate_file_type(upload: UploadFile, suffix: str) -> None:
    content_type = upload.content_type or ""
    if suffix.lower() in ALLOWED_EXTENSIONS or content_type.startswith("text/"):
        return
    raise UploadPolicyError("unsupported_file_type", f"Unsupported file type: {content_type or suffix or 'unknown'}")
