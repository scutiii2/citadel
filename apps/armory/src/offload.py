"""Runs a synchronous tool function off the asyncio event loop.
FastMCP calls a plain ``def`` tool inline and would freeze the server; ``@offload`` makes it async via ``asyncio.to_thread`` and keeps the schema through ``functools.wraps``. Apply it innermost, below ``@mcp.tool(...)``."""

from __future__ import annotations

import asyncio
import functools
import inspect
import typing
from typing import Any, Callable, TypeVar

from mcp.server.fastmcp import Context

from src.services import progress

F = TypeVar("F", bound=Callable[..., Any])


def offload(fn: F) -> F:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def offload_with_progress(fn: F) -> F:
    """``offload`` plus live progress: ``services.progress.report()`` calls from the worker thread reach the MCP client as ``notifications/progress``.
    Adds an optional ``ctx: Context`` parameter FastMCP injects; the wrapped function keeps its plain signature. Same decorator position as ``offload``."""
    # Resolve string annotations (``from __future__ import annotations``) in fn's own namespace,
    # since FastMCP evaluates the signature below without it.
    hints = typing.get_type_hints(fn, include_extras=True)
    signature = inspect.signature(fn)
    signature = signature.replace(
        parameters=[p.replace(annotation=hints.get(p.name, p.annotation)) for p in signature.parameters.values()],
        return_annotation=hints.get("return", signature.return_annotation),
    )

    @functools.wraps(fn)
    async def wrapper(*args: Any, ctx: Context | None = None, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        pending: list[Any] = []
        counter = 0

        def sink(message: str) -> None:
            nonlocal counter
            if ctx is None:
                return
            counter += 1
            pending.append(asyncio.run_coroutine_threadsafe(ctx.report_progress(counter, None, message), loop))

        token = progress.bind(sink)
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        finally:
            progress.reset(token)
            # Deliver every queued notification before the result goes out.
            await asyncio.gather(*(asyncio.wrap_future(f) for f in pending), return_exceptions=True)

    wrapper.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=[
            *signature.parameters.values(),
            inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=Context),
        ]
    )
    wrapper.__annotations__ = {**hints, "ctx": Context}
    return wrapper  # type: ignore[return-value]
