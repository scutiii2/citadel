"""Real-model MCP smoke check with a temporary specialist and a live Laya service.

Run from apps/legion: python -m scripts.check_laya_model
Exercises server.ask/status through the same MCP protocol Ember uses, using
stdio so this check does not bind a port or alter the live agent registry.
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from scripts.check_laya_triage import TRIAGE_QUESTIONS

PROJECT = Path(__file__).resolve().parents[1]


async def check() -> None:
    with tempfile.TemporaryDirectory(prefix="laya-triage-check-") as directory:
        spec_path = Path(directory) / "triage-assistant.json"
        spec = json.loads((PROJECT / "agents" / "triage-assistant.json").read_text(encoding="utf-8"))
        spec["llm"]["strategy"] = "laya-only"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if key not in ("AI_AGENT_PROVIDER", "AI_AGENT_MODEL", "AI_AGENT_GATEWAY", "CLAUDE_API_KEY", "GPT_API_KEY")}
        env["AI_AGENT_FILE"] = str(spec_path)
        env["AI_AGENT_USAGE_DIR"] = directory
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "import faulthandler; faulthandler.dump_traceback_later(60); from src import server; from src.providers.decision import provider; provider.prepare(); faulthandler.cancel_dump_traceback_later(); server.mcp.run(transport='stdio')"],
            cwd=str(PROJECT), env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize()
                status = await session.call_tool("status", {})
                status_data = json.loads(status.content[0].text)
                assert status_data["provider_id"] == "decision"
                assert status_data["context_window"] is None
                result = await session.call_tool("ask", {"question": json.dumps({"text": "SQLite database is locked; the SQL write failed.", "questions": TRIAGE_QUESTIONS})})
                assert not result.isError, result.content
                data = json.loads(result.content[0].text)
                assert data["provider_id"] == "decision"
                assert data["output_tokens"] == 0
                assert data["tools_used"] == []
                answers = json.loads(data["response"])["answers"]
                assert answers["category"]["choice"] == "database", answers
                assert data["agent_usage"][0]["agent_id"] == "triage-assistant"
                assert data["agent_usage"][0]["gateway"] is None
                print(json.dumps({"mcp_check": "passed", "provider": data["provider_id"],
                                  "response": data["response"], "input_tokens": data["input_tokens"],
                                  "output_tokens": data["output_tokens"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(check())
