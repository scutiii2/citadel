"""PDFs need no conversion; this converter only validates them."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.capabilities.pdf_merger.utils.converters.base import ImageOptions
from src.services.user_files.pdfs import count_pages


class PdfPassthrough:
    kind = "pdf"

    def can_handle(self, mime: str) -> bool:
        return mime == "application/pdf"

    async def inspect(self, path: Path) -> int:
        return await asyncio.to_thread(count_pages, path)

    async def to_pdf(self, path: Path, work_dir: Path, opts: ImageOptions) -> Path:
        return path
