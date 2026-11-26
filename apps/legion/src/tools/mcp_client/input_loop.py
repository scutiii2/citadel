"""The rounds of one tool call on a 2026-07-28 connection, where a server may ask for input first."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp_types import ElicitRequest, ElicitRequestParams, ElicitResult, InputRequiredResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

MAX_INPUT_ROUNDS = 5

# (server label from our configuration, tool name, the question) -> the user's answer
Elicit = Callable[[str, str, ElicitRequestParams], Awaitable[ElicitResult]]
Ask = Callable[[ElicitRequestParams], Awaitable[ElicitResult]]


def speaks_input(session: Any) -> bool:
    return getattr(session, "protocol_version", None) in MODERN_PROTOCOL_VERSIONS


async def call_with_input(send: Callable[..., Awaitable[Any]], ask: Ask | None) -> Any:
    """`send(**round_arguments)` sends one round on one session. Every retry uses that session, so a
    failed round is never replayed elsewhere. With no `ask`, every question is declined."""
    result = await send(allow_input_required=True)
    for _ in range(MAX_INPUT_ROUNDS):
        if not isinstance(result, InputRequiredResult):
            return result
        responses = {}
        for key, request in (result.input_requests or {}).items():
            if not isinstance(request, ElicitRequest):  # sampling and roots are not offered
                raise RuntimeError("The server asked for something Citadel does not provide")
            responses[key] = await ask(request.params) if ask else ElicitResult(action="decline")
        again: dict[str, Any] = {"allow_input_required": True}
        if responses:
            again["input_responses"] = responses
        if result.request_state is not None:
            again["request_state"] = result.request_state
        result = await send(**again)
    if isinstance(result, InputRequiredResult):
        raise RuntimeError(f"The server asked for input more than {MAX_INPUT_ROUNDS} times")
    return result
