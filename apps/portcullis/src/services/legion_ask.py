"""One stateless ask to Legion's entry agent as an outside client: no extensions, every tool refused,
no plan tool, no questions back, no memory of earlier calls beyond the history the client sends."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

import httpx

from src.models.outside_client import OutsideClient
# Not root_cause(): an SDK error's text can echo the arguments, so only the exception type is kept.
from src.services.mcp_session import identity_headers, mcp_session

_log = logging.getLogger(__name__)

ASK_SECONDS = 120
_TIMEOUT = httpx.Timeout(30.0, read=ASK_SECONDS)
DISABLED_TOOLS = ["*"]


class LegionUnavailable(Exception):
    """Legion did not answer; the message never holds the question or answer."""


@dataclass(frozen=True)
class LegionAnswer:
    text: str
    tokens: int
    request_id: str


def _tokens(data: dict) -> int:
    usage = data.get("agent_usage")
    if isinstance(usage, list) and usage:
        return sum(int(row.get("total_tokens") or 0) for row in usage if isinstance(row, dict))
    return int(data.get("total_tokens") or 0)


class LegionAsk:
    async def ask(self, url: str, client: OutsideClient, question: str, history: list[dict]) -> LegionAnswer:
        request_id = uuid.uuid4().hex
        arguments = {
            "question": question, "history": history, "enabled_extensions": [], "approval_mode": "deny",
            "allowed_tools": [], "plan": False, "ask_user": False, "caveman": False, "request_id": request_id,
            # deny + allowed_tools=[] only gates the model's tool loop; Legion's memory recall, skill recall and
            # skill learning call mcp_upstream.call_tool directly. "*" is Legion's tool_filter wildcard, checked
            # first in call_tool, and delegation passes it on to every delegate.
            "disabled_tools": DISABLED_TOOLS,
        }
        try:
            async with asyncio.timeout(ASK_SECONDS):
                async with mcp_session(url, identity_headers(client.name, "", client.uid), _TIMEOUT) as session:
                    result = await session.call_tool("ask", arguments)
        except Exception as error:  # noqa: BLE001 - includes the SDK's ExceptionGroup wrappers and the timeout
            raise LegionUnavailable(f"Legion is unavailable: {type(error).__name__}") from None
        data = result.structuredContent if not result.isError else None
        text = data.get("response") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise LegionUnavailable("Legion gave no answer")
        try:
            tokens = _tokens(data)
        except (TypeError, ValueError):
            tokens = 0
        if tokens == 0:
            _log.warning("outside call %s: Legion reported no tokens", request_id)
        return LegionAnswer(text=text, tokens=tokens, request_id=request_id)
