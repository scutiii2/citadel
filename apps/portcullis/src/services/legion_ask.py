"""Ask Legion's entry agent as an outside client, optionally with access to its own Brain notes."""

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
STRONGHOLD_ALLOWED = (
    "stronghold__tool_brain_search", "stronghold__tool_brain_read", "stronghold__tool_brain_list",
    "stronghold__tool_brain_write", "stronghold__tool_brain_update",
)


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
        return max(0, sum(max(0, int(row.get("total_tokens") or 0)) for row in usage if isinstance(row, dict)))
    return max(0, int(data.get("total_tokens") or 0))


class LegionAsk:
    async def ask(self, url: str, client: OutsideClient, question: str, history: list[dict], *,
                  memory: bool = False) -> LegionAnswer:
        request_id = uuid.uuid4().hex
        allowed = list(STRONGHOLD_ALLOWED) if memory else []
        arguments = {
            "question": question, "history": history, "approval_mode": "deny",
            "allowed_tools": allowed, "plan": False, "ask_user": False, "caveman": False, "request_id": request_id,
            # Approvals gate the model's tool loop. Recall and skill learning also call the upstream directly,
            # so block every tool there too. The Brain search exception permits memory recall.
            "disabled_tools": ["*", *(f"!{tool}" for tool in allowed)],
        }
        try:
            async with asyncio.timeout(ASK_SECONDS):
                async with mcp_session(url, identity_headers(f"outside:{client.uid}", "", client.uid), _TIMEOUT) as session:
                    result = await session.call_tool("ask", arguments)
        except Exception as error:  # noqa: BLE001 - includes the SDK's ExceptionGroup wrappers and the timeout
            raise LegionUnavailable(f"Legion is unavailable: {type(error).__name__}") from None
        data = result.structuredContent if not result.isError else None
        text = data.get("response") if isinstance(data, dict) else None
        # Legion answers a cancelled run with a "Cancelled." text, which is not an answer.
        if not isinstance(text, str) or not text.strip() or data.get("cancelled"):
            raise LegionUnavailable("Legion gave no answer")
        try:
            tokens = _tokens(data)
        except (TypeError, ValueError):
            tokens = 0
        if tokens == 0:
            _log.warning("outside call %s: Legion reported no tokens", request_id)
        return LegionAnswer(text=text, tokens=tokens, request_id=request_id)
