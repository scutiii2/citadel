"""Numbered tool failures: a tool that cannot reach a dependency says which one and whether to retry."""

from __future__ import annotations

import re
from enum import IntEnum

import httpx


class Code(IntEnum):
    TOOL_INTERNAL = 1000
    DEP_NOT_CONFIGURED = 1001
    DEP_UNAVAILABLE = 1002
    DEP_TIMEOUT = 1003
    DEP_AUTH_REJECTED = 1004
    DEP_ERROR = 1005


_RETRYABLE = {
    Code.TOOL_INTERNAL: False,
    Code.DEP_NOT_CONFIGURED: False,
    Code.DEP_UNAVAILABLE: True,
    Code.DEP_TIMEOUT: True,
    Code.DEP_AUTH_REJECTED: False,
    Code.DEP_ERROR: None,  # maybe
}
_WORDS = {
    Code.TOOL_INTERNAL: "failed",
    Code.DEP_NOT_CONFIGURED: "not configured",
    Code.DEP_UNAVAILABLE: "unavailable",
    Code.DEP_TIMEOUT: "timed out",
    Code.DEP_AUTH_REJECTED: "rejected the service token",
    Code.DEP_ERROR: "returned an error",
}
_LINE = re.compile(r"^\[(\d{4})\] ([A-Z_]+) (.*)$")


class Failure(Exception):
    """A failure with a number. `text` is safe to show to a model or a user."""

    def __init__(self, code: Code, dependency: str = "") -> None:
        self.code = Code(code)
        self.dependency = dependency
        super().__init__(self.text)

    @property
    def message(self) -> str:
        return _WORDS[self.code]

    @property
    def retryable(self) -> bool | None:
        return _RETRYABLE[self.code]

    @property
    def text(self) -> str:
        subject = self.dependency or "tool"
        return f"[{int(self.code)}] {self.code.name} {subject} {self.message}"


def from_exception(dependency: str, error: BaseException) -> Failure:
    """Map a transport error to a code. Never copies the error's own text."""
    if isinstance(error, Failure):
        return error
    if isinstance(error, httpx.TimeoutException):
        return Failure(Code.DEP_TIMEOUT, dependency)
    if isinstance(error, (httpx.ConnectError, httpx.NetworkError)):
        return Failure(Code.DEP_UNAVAILABLE, dependency)
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in (401, 403):
            return Failure(Code.DEP_AUTH_REJECTED, dependency)
        return Failure(Code.DEP_ERROR, dependency)
    return Failure(Code.TOOL_INTERNAL, dependency)


def parse(text: str) -> Failure | None:
    """Read a failure back from its text form, or None when the text is not one."""
    line = text.strip()
    match = _LINE.fullmatch(line)
    if not match:
        return None
    try:
        code = Code(int(match.group(1)))
    except ValueError:
        return None
    if code.name != match.group(2):
        return None
    subject, separator, message = match.group(3).partition(" ")
    if not subject or not separator or message != _WORDS[code]:
        return None
    return Failure(code, "" if subject == "tool" else subject)
