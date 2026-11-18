"""Calls ai_agent's Laya agent over MCP: its `ask` tool takes the typed-question
JSON as `question` and returns a dict whose `response` is the answer JSON."""

from __future__ import annotations

import json
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from src.citadel_auth import ServiceAuth, requester_meta
from src.services.service_auth import keyring


def parse_laya_reply(result: dict[str, Any]) -> dict[str, Any]:
    """The Laya answer object inside ai_agent's `ask` result; ValueError if it is anything else."""
    raw = result.get("response")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Laya returned no response.")
    try:
        reply = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("Laya returned a response that is not JSON.") from error
    if not isinstance(reply, dict) or not isinstance(reply.get("answers"), dict):
        raise ValueError("Laya returned no answers.")
    return reply


class McpLayaTransport:
    def __init__(self, url: str) -> None:
        self._url = url

    async def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with streamablehttp_client(self._url, auth=ServiceAuth(keyring, "legion")) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("ask", {"question": json.dumps(payload)}, meta=requester_meta())
        if result.isError:
            raise ValueError("Laya reported an error.")
        data = result.structuredContent
        if not isinstance(data, dict):
            text = next((block.text for block in result.content if getattr(block, "text", None)), "")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError("Laya returned an unreadable result.") from error
        return parse_laya_reply(data)
