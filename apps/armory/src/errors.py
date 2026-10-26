"""Turn an unexpected exception into something safe to show; mirrors chat_app/src/errors.py.
`str(exc)` can leak paths, hostnames or credentials, so detail goes only to server.log and a per-reference file under log_dir/errors/."""

from __future__ import annotations

import logging
import secrets
import traceback

from src.config import settings

logger = logging.getLogger("mcp_server")


def report(exc: Exception, *, context: str) -> str:
    """Log ``exc`` with a fresh reference id and return a message safe to display."""
    reference = secrets.token_hex(4)
    logger.exception("[%s] %s", reference, context, exc_info=exc)
    _write_error_file(exc, reference=reference, context=context)
    return (
        f"Something went wrong while {context}. "
        f"The details are in the server log under reference {reference}."
    )


def _write_error_file(exc: Exception, *, reference: str, context: str) -> None:
    errors_dir = settings.log_dir / "errors"
    errors_dir.mkdir(parents=True, exist_ok=True)
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    (errors_dir / f"{reference}.log").write_text(
        f"reference: {reference}\ncontext: {context}\n\n{trace}", encoding="utf-8"
    )
