"""Adapter: MinerU content_list.json -> LangExtract-ready input + structured table triples.

Per docs/mineru_specification-v1.0.md (real content_list.json schema: flat list of
blocks with type in {"text","table"}, text/text_level, table_body HTML, bbox 0-1000
normalized, page_idx) and docs/langextract_specification-v1.0.md (lx.extract()
char_interval semantics). Splits blocks into two lanes:
  - Lane A (tables): parsed directly from table_body HTML, no LLM involved.
  - Lane B (text): concatenated per page with an offset map so LangExtract's
    char_interval can be traced back to the originating block's page_idx/bbox.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup


def load_content_list(content_list_path: str | pathlib.Path) -> list[dict[str, Any]]:
    path = pathlib.Path(content_list_path)
    return json.loads(path.read_text(encoding="utf-8"))


def group_by_page(blocks: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    pages: dict[int, list[dict[str, Any]]] = {}
    for block in blocks:
        pages.setdefault(block["page_idx"], []).append(block)
    return pages


# --- Lane A: structured tables (no LLM) ----------------------------------------


def parse_table_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a MinerU table block's HTML into row/column/value triples.

    Assumes the first row is the header row and its first cell is the row-label
    column header (matches every real sample observed in content_list.json).
    """
    html = block.get("table_body", "")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        return []

    header_cells = [td.get_text(strip=True) for td in rows[0].find_all("td")]
    column_names = header_cells[1:]

    triples = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells:
            continue
        row_label, values = cells[0], cells[1:]
        for column_name, value in zip(column_names, values):
            triples.append({
                "row_label": row_label,
                "metric": column_name,
                "value": value,
                "provenance": {
                    "page_idx": block["page_idx"],
                    "bbox": block["bbox"],
                    "img_path": block.get("img_path"),
                    "block_type": "table",
                },
            })
    return triples


# --- Lane B: text concatenation + offset map ------------------------------------


@dataclass
class OffsetEntry:
    start: int
    end: int
    block_index: int
    page_idx: int
    bbox: list[int]


@dataclass
class PageText:
    page_idx: int
    text: str
    offsets: list[OffsetEntry]


def build_page_text(page_idx: int, blocks: list[dict[str, Any]]) -> PageText:
    """Concatenate a page's text blocks (in MinerU reading order) with an offset map.

    Only type=="text" blocks contribute; tables are handled by parse_table_block.
    """
    text_blocks = [(i, b) for i, b in enumerate(blocks) if b.get("type") == "text"]

    parts: list[str] = []
    offsets: list[OffsetEntry] = []
    cursor = 0
    for block_index, block in text_blocks:
        block_text = block["text"]
        start = cursor
        end = start + len(block_text)
        offsets.append(OffsetEntry(
            start=start,
            end=end,
            block_index=block_index,
            page_idx=page_idx,
            bbox=block["bbox"],
        ))
        parts.append(block_text)
        cursor = end + 2  # "\n\n" separator

    return PageText(page_idx=page_idx, text="\n\n".join(parts), offsets=offsets)


def find_provenance(
    char_start: int, char_end: int, offsets: list[OffsetEntry]
) -> OffsetEntry | None:
    """Find the offset entry whose source block overlaps [char_start, char_end)."""
    for entry in offsets:
        if entry.start <= char_start < entry.end or entry.start < char_end <= entry.end:
            return entry
    return None


def load_pages(
    content_list_path: str | pathlib.Path,
) -> tuple[list[PageText], list[dict[str, Any]]]:
    """Load a MinerU content_list.json, split into (Lane B page texts, Lane A table blocks)."""
    blocks = load_content_list(content_list_path)
    pages = group_by_page(blocks)

    page_texts = [
        build_page_text(page_idx, page_blocks)
        for page_idx, page_blocks in sorted(pages.items())
    ]
    table_blocks = [b for b in blocks if b.get("type") == "table"]

    return page_texts, table_blocks
