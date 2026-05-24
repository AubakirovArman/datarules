from pathlib import Path

from .common import CanonicalBlock, ParseResult, ParserError


def parse_pdf(path: Path, image_dir: Path | None = None) -> ParseResult:
    try:
        import fitz
    except ImportError as exc:
        raise ParserError("PyMuPDF is required for PDF parsing") from exc

    document = fitz.open(path)
    blocks: list[CanonicalBlock] = []
    rendered_pages: list[str] = []

    for page_index, page in enumerate(document, start=1):
        text_dict = page.get_text("dict")
        text_found = False
        for raw_block in text_dict.get("blocks", []):
            lines = raw_block.get("lines", [])
            text = "\n".join(
                "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                for line in lines
            ).strip()
            if not text:
                continue
            text_found = True
            blocks.append(
                CanonicalBlock(
                    block_type="paragraph",
                    page=page_index,
                    text=text,
                    bbox=[float(v) for v in raw_block.get("bbox", [])],
                    confidence=0.96,
                )
            )

        if not text_found and image_dir:
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / f"{path.stem}_page_{page_index:04d}.png"
            page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(image_path)
            rendered_pages.append(str(image_path))
            blocks.append(
                CanonicalBlock(
                    block_type="image_page",
                    page=page_index,
                    text="",
                    confidence=0.4,
                    metadata={"image_path": str(image_path), "requires_multimodal_ocr": True},
                )
            )

    return ParseResult(
        file_type="pdf",
        blocks=blocks,
        metadata={"pages": document.page_count, "rendered_pages": rendered_pages},
    )
