import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CanonicalBlock:
    block_type: str
    text: str = ""
    page: int | None = None
    sheet_name: str | None = None
    slide_number: int | None = None
    table_json: Any = None
    bbox: list[float] | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    file_type: str
    blocks: list[CanonicalBlock]
    metadata: dict[str, Any] = field(default_factory=dict)


class ParserError(RuntimeError):
    pass


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-16", "cp1251", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


CONTROL_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str | None) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return CONTROL_TEXT.sub("", text)


def clean_json(value: Any) -> Any:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    if isinstance(value, dict):
        return {clean_text(str(key)): clean_json(item) for key, item in value.items()}
    return value


def split_paragraphs(text: str, limit: int = 2200) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append("\n".join(current))
                current, current_len = [], 0
            continue
        if current_len + len(line) > limit and current:
            paragraphs.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)

    if current:
        paragraphs.append("\n".join(current))
    return paragraphs or ([text.strip()] if text.strip() else [])
