"""Keeps account uids out of the request lines HTTPX logs.

Portcullis calls Armory (`/skills/owners/<uid>`) and Stronghold (`/<domain>/accounts/<uid>`)
with the uid in the path, and HTTPX logs every request URL at INFO.
"""

from __future__ import annotations

import logging
import re

_UID_IN_PATH = re.compile(r"(/(?:owners|accounts)/)[^\s\"?]+")


def redact(text: str) -> str:
    """`text` with any account uid in a path replaced."""
    return _UID_IN_PATH.sub(r"[redacted]", text)


class UidLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        def redact(value):
            text = str(value)
            return _UID_IN_PATH.sub(r"\1[redacted]", text) if "/owners/" in text or "/accounts/" in text else value

        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        return True


def install() -> None:
    """Idempotent: one filter on each logger that prints request lines (`httpx` for calls made,
    `uvicorn.access` for calls received, such as Stronghold's `/internal/accounts/<uid>/...`)."""
    for name in ("httpx", "uvicorn.access"):
        request_logger = logging.getLogger(name)
        if not any(isinstance(f, UidLogFilter) for f in request_logger.filters):
            request_logger.addFilter(UidLogFilter())
