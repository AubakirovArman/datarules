from pathlib import Path

from .common import ParseResult, ParserError
from .csv_parser import parse_csv
from .office import parse_docx, parse_pptx, parse_xlsx
from .pdf import parse_pdf
from .text import parse_text


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".json", ".xml"}


def parse_document(path: Path, content_type: str, image_dir: Path) -> ParseResult:
    ext = path.suffix.lower()

    if ext == ".pdf" or content_type == "application/pdf":
        return parse_pdf(path, image_dir=image_dir)
    if ext == ".csv" or content_type in {"text/csv", "application/csv"}:
        return parse_csv(path)
    if ext in {".xlsx", ".xlsm"}:
        return parse_xlsx(path)
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".pptx":
        return parse_pptx(path)
    if ext in TEXT_EXTENSIONS or content_type.startswith("text/"):
        return parse_text(path)

    raise ParserError(f"Unsupported file type: {content_type or ext}")
