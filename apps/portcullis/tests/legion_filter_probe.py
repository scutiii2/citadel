"""Run with Legion's own Python, cwd apps/legion (see test_legion_ask.py). Not a test module.

Reads the `disabled_tools` value Portcullis sends on stdin (JSON), binds it the way Legion's run_chat does,
and drives Legion's real recall, skill recall and skill learning paths plus mcp_upstream.call_tool against a
fake upstream client that records every tool call. Prints JSON: the calls that reached the upstream and how
each direct call ended. Imports no agent_config/server, so no .env is read or seeded and no model runs.
"""

import asyncio
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, ".")

from src.agents.roles.orchestrator import memory_recall, skill_recall, skill_reflection  # noqa: E402
from src.providers.base_provider import ChatResult, ToolCallRecord  # noqa: E402
from src.runtime import tool_filter  # noqa: E402
from src.tools.mcp_client import mcp_upstream  # noqa: E402

TOOLS = [memory_recall.TOOL, skill_recall.TOOL, skill_reflection.TOOL, "main__tool_ticket_list"]
calls: list[str] = []


class Upstream:
    def list_tools(self):
        return [SimpleNamespace(name=name) for name in TOOLS]

    def call_tool(self, name, arguments, **kwargs):
        calls.append(name)
        return SimpleNamespace(content=[SimpleNamespace(text='{"ok": true, "results": []}')])


async def draft(question, found, request_id):
    return {"title": "t", "when_to_use": "w", "steps": "s", "tools": "x"}


async def drive() -> dict:
    recalled = await memory_recall.with_recall("q")
    skilled = await skill_recall.with_skills("q", "q")
    turn = ChatResult(response="answer", tool_calls=[ToolCallRecord(f"main__tool_{i}", {}, "refused") for i in "abc"])
    task = skill_reflection.schedule("q", turn, "r")
    proposed = await task if task else None
    direct = {}
    for name in TOOLS:
        try:
            await asyncio.to_thread(mcp_upstream.call_tool, name, {})
            direct[name] = "ran"
        except Exception as error:  # noqa: BLE001 - the probe reports the type only
            direct[name] = type(error).__name__
    return {"recall_unchanged": recalled == "q", "skills_unchanged": skilled == "q", "proposed": proposed, "direct": direct}


def main() -> None:
    disabled = json.load(sys.stdin)
    mcp_upstream.client = Upstream()
    mcp_upstream.internal_auth.requester_meta = lambda: None
    skill_reflection._draft = draft
    token = tool_filter.bind(disabled)
    try:
        result = asyncio.run(drive())
    finally:
        tool_filter.reset(token)
    print(json.dumps({**result, "upstream_calls": calls}))


main()
