from pathlib import Path

from .common import CanonicalBlock, ParseResult, read_text, split_paragraphs


def parse_text(path: Path) -> ParseResult:
    text = read_text(path)
    blocks = [
        CanonicalBlock(block_type="paragraph", text=part, confidence=1.0)
        for part in split_paragraphs(text)
    ]
    return ParseResult(file_type="text", blocks=blocks, metadata={"characters": len(text)})
