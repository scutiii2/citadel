"""Turn a dependency failure inside a Stronghold tool into numbered text a model can act on."""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from src.citadel_auth.failure import Code, Failure, from_exception
from src.document_store import DbGatewayError, DbGatewayUnavailable


def _storage_failure(dependency: str, error: Exception) -> Failure:
    if isinstance(error, DbGatewayUnavailable):
        cause = error.__cause__
        if isinstance(cause, httpx.RemoteProtocolError):
            return Failure(Code.DEP_UNAVAILABLE, dependency)
        if isinstance(cause, httpx.TransportError):
            return from_exception(dependency, cause)
        return Failure(Code.DEP_UNAVAILABLE, dependency)
    if isinstance(error, DbGatewayError):
        code = Code.DEP_AUTH_REJECTED if error.status in (401, 403) else Code.DEP_ERROR
        return Failure(code, dependency)
    return from_exception(dependency, error)


def guarded(dependency: str):
    def wrap(tool: Callable[..., Awaitable[Any]]):
        @functools.wraps(tool)
        async def run(*args, **kwargs):
            try:
                return await tool(*args, **kwargs)
            except Exception as error:  # the text never carries the exception's own message
                return _storage_failure(dependency, error).text

        return run

    return wrap
