import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_registry, agent_spec
from src.agents.roles.orchestrator import context_summarizer, delegation
from src.runtime import internal_auth
from src.providers import cancellation


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "test")
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "_AGENTS_BY_ID", {
        "context-summarizer": {"role": "specialist", "id": "context-summarizer", "url": "http://helper/mcp"},
    })
    call = AsyncMock(return_value={"response": "Investigate the failing server deployment.", "agent_usage": [
        {"agent_id": "context-summarizer", "total_tokens": 12},
    ]})
    monkeypatch.setattr(delegation, "_call_tool", call)
    return call


def test_routing_brief_uses_history_and_books_helper_usage(helper):
    usage, token = delegation.bind_usage()
    try:
        result = asyncio.run(context_summarizer.routing_brief("continue", [
            {"role": "assistant", "content": "Earlier summary: deployment failed; preserve the database."},
            {"role": "user", "content": "The server refuses connections."},
        ], "r"))
    finally:
        delegation.reset_usage(token)
    assert result == "Investigate the failing server deployment."
    url, operation, arguments = helper.call_args.args
    assert url == "http://helper/mcp" and operation == "interpret"
    assert "Mode: routing" in arguments["text"]
    assert "preserve the database" in arguments["text"]
    assert "refuses connections" in arguments["text"]
    assert "continue" in arguments["text"]
    assert len(usage) == 1
    assert usage[0]["agent_id"] == "context-summarizer" and usage[0]["request_id"] == "r"


def test_first_message_does_not_need_an_extra_model_call(helper):
    assert asyncio.run(context_summarizer.routing_brief("hello", [], "r")) is None
    helper.assert_not_called()


@pytest.mark.parametrize("response", ["", "x" * 1601, None, {"bad": "shape"}])
def test_unusable_summary_falls_back_but_still_books_usage(helper, response):
    helper.return_value["response"] = response
    usage, token = delegation.bind_usage()
    try:
        assert asyncio.run(context_summarizer.routing_brief("continue", [
            {"role": "user", "content": "Investigate the server."},
        ], "r")) is None
    finally:
        delegation.reset_usage(token)
    assert len(usage) == 1


def test_missing_agent_does_not_call_a_different_agent(helper, monkeypatch):
    monkeypatch.setattr(agent_registry, "_AGENTS_BY_ID", {})
    assert asyncio.run(context_summarizer.routing_brief("continue", [
        {"role": "user", "content": "Investigate the server."},
    ], "r")) is None
    helper.assert_not_called()


def test_transport_failure_falls_back(helper):
    helper.side_effect = RuntimeError("offline")
    assert asyncio.run(context_summarizer.routing_brief("continue", [
        {"role": "user", "content": "Investigate the server."},
    ], "r")) is None


def test_routing_prompt_is_bounded_and_keeps_early_summary_and_latest_intent(helper):
    asyncio.run(context_summarizer.routing_brief("latest exact instruction", [
        {"role": "assistant", "content": "Earlier summary: KEEP THIS CONSTRAINT"},
        {"role": "user", "content": "x" * 100000},
        {"role": "assistant", "content": "MOST RECENT CONTEXT"},
    ], "r"))
    prompt = helper.call_args.args[2]["text"]
    assert len(prompt) < 35000
    assert "KEEP THIS CONSTRAINT" in prompt and "MOST RECENT CONTEXT" in prompt
    assert "latest exact instruction" in prompt and "omitted" in prompt


def test_cancelled_request_does_not_call_helper(helper):
    cancellation.cancel("cancelled-summary")
    try:
        assert asyncio.run(context_summarizer.routing_brief("continue", [
            {"role": "user", "content": "Investigate the server."},
        ], "cancelled-summary")) is None
    finally:
        cancellation.clear("cancelled-summary")
    helper.assert_not_called()


def test_slow_helper_times_out(helper, monkeypatch):
    async def slow(*args):
        await asyncio.sleep(1)
    helper.side_effect = slow
    monkeypatch.setattr(context_summarizer, "ROUTING_TIMEOUT_SECONDS", .01)
    assert asyncio.run(context_summarizer.routing_brief("continue", [
        {"role": "user", "content": "Investigate the server."},
    ], "r")) is None


def test_cancellation_during_summary_discards_late_response(helper):
    async def cancelled_response(*args):
        cancellation.cancel("cancel-in-flight")
        return {"response": "Should never route", "agent_usage": []}
    helper.side_effect = cancelled_response
    try:
        assert asyncio.run(context_summarizer.routing_brief("continue", [
            {"role": "user", "content": "Investigate the server."},
        ], "cancel-in-flight")) is None
    finally:
        cancellation.clear("cancel-in-flight")


def test_agent_definition_is_a_light_tool_free_helper():
    spec = agent_spec.load_file(Path(__file__).parents[1] / "agents" / "context-summarizer.json")
    assert spec.enabled and not spec.entry and not spec.orchestrator and not spec.delegable
    assert not spec.memory_recall and not spec.plan_tool
    assert spec.tools.deny == ("*",)
    assert spec.llm.min_tier == spec.llm.max_tier == "light"
