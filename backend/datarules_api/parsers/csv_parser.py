import csv
from pathlib import Path

from .common import CanonicalBlock, ParseResult, read_text


def parse_csv(path: Path) -> ParseResult:
    text = read_text(path)
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
    rows = list(csv.reader(text.splitlines(), dialect=dialect))

    blocks = [
        CanonicalBlock(
            block_type="table",
            table_json={"rows": rows},
            text="\n".join(",".join(cell for cell in row) for row in rows[:50]),
            confidence=1.0,
        )
    ]
    return ParseResult(file_type="csv", blocks=blocks, metadata={"rows": len(rows)})
