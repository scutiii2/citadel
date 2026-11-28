"""The text of a scan, an image or audio, read by Reader or Scribe when they can."""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException

from src.attachments.extraction import MAX_TEXT_CHARS
from src.tool_services.client import ToolServices

logger = logging.getLogger(__name__)

BUDGET_SECONDS = 110  # under Portcullis's 150 s upload timeout, which also covers the Armory store
_PAGE_MARK = "<PAGE>"  # Reader puts one before each page


def _usable(text: object) -> tuple[str, bool] | None:
    """(text, truncated) cut like every attachment, or None when there is nothing to attach."""
    if not isinstance(text, str) or not text.replace(_PAGE_MARK, "").strip():
        return None
    text = text.strip()
    return text[:MAX_TEXT_CHARS], len(text) > MAX_TEXT_CHARS


async def read_with_reader(connections: ToolServices, suffix: str, content: bytes) -> tuple[str, bool] | None:
    """(text, truncated) from Reader, or None when it cannot read the file: the model is then shown the pages."""
    try:
        async with asyncio.timeout(BUDGET_SECONDS):
            # A fixed name: the connection refuses non-ASCII ones, and Reader judges the file by its bytes.
            uploaded = await connections.post_file("/connections/reader/files", f"document{suffix}", content)
            result = await connections.call("POST", "/connections/reader/parse", {"file_id": uploaded.get("file_id")})
    except (HTTPException, TimeoutError):
        return None
    return _usable(result.get("text"))


async def transcribe_with_scribe(connections: ToolServices, suffix: str, content: bytes) -> tuple[str, bool] | None:
    """(transcript, truncated) from Scribe, or None when it cannot give one: Legion then transcribes the file."""
    try:
        async with asyncio.timeout(BUDGET_SECONDS):
            result = await connections.post_file("/connections/scribe/transcribe", f"audio{suffix}", content)
    except HTTPException as error:
        logger.warning("Scribe transcription failed: status %s, request refused or service unavailable", error.status_code)
        return None
    except TimeoutError:
        logger.warning("Scribe transcription failed: status timeout, time budget exceeded")
        return None
    text = _usable(result.get("text"))
    if text is None:
        logger.warning("Scribe transcription failed: status 200, no usable transcript")
    return text
