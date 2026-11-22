"""Turn an unexpected exception into something safe to show; mirrors chat_app/src/errors.py.
`str(exc)` can leak paths, hostnames or credentials, so detail goes only to server.log and a per-reference file under log_dir/errors/."""

from __future__ import annotations

import asyncio
import functools
import logging
import smtplib
from urllib.error import HTTPError, URLError
import secrets
import traceback

import httpx

from src.citadel_auth.failure import Code, Failure, from_exception
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

class DependencyToolError(RuntimeError):
    """Safe numbered failure for the MCP tool boundary."""


def dependency_failure(dependency: str, error: BaseException) -> str:
    """Translate a known outside-service failure without exposing its text."""
    if isinstance(error, (Failure, httpx.HTTPError)):
        return from_exception(dependency, error).text
    cause = error.__cause__ or error.__context__ or error
    if isinstance(cause, httpx.HTTPError):
        return from_exception(dependency, cause).text
    if isinstance(cause, HTTPError):
        code = Code.DEP_AUTH_REJECTED if cause.code in (401, 403) else Code.DEP_ERROR
    elif isinstance(cause, smtplib.SMTPAuthenticationError):
        code = Code.DEP_AUTH_REJECTED
    elif dependency == "smtp" and not isinstance(cause, ConnectionRefusedError):
        # Delivery may have been accepted already.
        code = Code.DEP_ERROR
    elif isinstance(cause, TimeoutError) or (isinstance(cause, URLError) and isinstance(cause.reason, TimeoutError)):
        code = Code.DEP_TIMEOUT
    elif isinstance(cause, (URLError, ConnectionError)):
        code = Code.DEP_UNAVAILABLE
    else:
        code = Code.DEP_ERROR
    return Failure(code, dependency).text


def numbered_dependency(dependency: str, *errors: type[Exception]):
    """Keep the FastMCP success schema and give dependency errors plain text."""
    def decorate(tool):
        @functools.wraps(tool)
        async def invoke(*args, **kwargs):
            try:
                return await tool(*args, **kwargs)
            except (httpx.HTTPError, Failure, *errors) as error:
                raise DependencyToolError(dependency_failure(dependency, error)) from None
            except ValueError:
                raise  # Existing argument validation messages remain actionable.
            except Exception as error:
                try:
                    message = await asyncio.to_thread(report, error, context=f"running {tool.__name__}")
                except OSError:
                    message = Failure(Code.TOOL_INTERNAL, dependency).text
                raise DependencyToolError(message) from None

        return invoke

    return decorate
