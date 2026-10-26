"""Parse a page selection like "1-3,7" into 0-based indices, keeping the written order.
Duplicate detection is the planner's job, since it spans segments."""

from __future__ import annotations

import re

from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError

_PART = re.compile(r"(\d+)(?:\s*-\s*(\d+))?")


def parse_page_ranges(spec: str | None, page_count: int) -> list[int]:
    """Return 0-based indices. None, "", or "all" select every page. O(n) in pages selected."""
    text = (spec or "").strip()
    if text == "" or text.lower() == "all":
        return list(range(page_count))

    pages: list[int] = []
    for raw in text.split(","):
        part = raw.strip()
        match = _PART.fullmatch(part)
        if match is None:
            raise MergerError(ErrorCode.INVALID_RANGE, f'"{part}" isn\'t a page or range. Use a form like 1-3,7.')
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start > end:
            raise MergerError(ErrorCode.INVALID_RANGE, f'"{part}" runs backwards. Write the lower page first.')
        if start < 1 or end > page_count:
            raise MergerError(ErrorCode.INVALID_RANGE, f'"{part}" is outside the document. Pages go from 1 to {page_count}.')
        pages.extend(range(start - 1, end))
    return pages
