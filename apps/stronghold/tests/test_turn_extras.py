"""Turn behaviour that Portcullis's tests used to cover: storage failures, the chat trace, usage trouble."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.document_store import DbGatewayError
from tests.test_turns import agent  # noqa: F401  (the Legion stand-in fixture)
from tests.test_turns import AGENT_ID, chat, events, new_id, start, wait_until
from tests.turn_agent import TurnAgent

TRACE_ROWS = [
    {
        "agent_id": "claude-agent", "agent_label": "Ember", "provider_id": "anthropic", "gateway": "openrouter",
        "model": "claude-test", "input_tokens": 70, "output_tokens": 30, "total_tokens": 100,
        "started_at": "2026-10-04T09:12:03.512Z", "finished_at": "2026-10-04T09:12:07.044Z", "delegated_by": None,
        "model_tier": "heavy", "reasoning_effort": "low",
        "prompt": [{"role": "user", "content": "earlier"}, {"role": "user", "content": "add 2 and 3"}],
    },
    {
        "agent_id": "calc", "agent_label": "Calculator", "provider_id": "openai", "gateway": None,
        "model": "gpt-x", "input_tokens": 20, "output_tokens": 5, "total_tokens": 25,
        "started_at": "2026-10-04T09:12:04.000Z", "finished_at": "2026-10-04T09:12:05.250Z", "delegated_by": "claude-agent",
        "prompt": [{"role": "user", "content": "2 + 3"}],
    },
]


def fail_collection(db_gateway, name: str) -> None:
    """Reads of this collection fail, as when Treasury is down."""
    for method in ("get", "query"):
        real = getattr(db_gateway, method)

        async def broken(collection, *args, _real=real, **kwargs):
            if collection == name:
                raise DbGatewayError("down")
            return await _real(collection, *args, **kwargs)

        setattr(db_gateway, method, broken)


def traces(platform) -> list[dict]:
    return [line for line in platform.logs if line["kind"] == "chat_trace"]


# --- storage failures ---------------------------------------------------------------------


def test_without_the_switched_off_list_the_turn_is_refused_rather_than_offering_every_agent(client: TestClient, db_gateway, agent: TurnAgent) -> None:
    fail_collection(db_gateway, "account_agents")
    assert start(client, new_id()).status_code == 503
    assert agent.asks == []


def test_the_browser_cannot_name_tools_to_switch_off(client: TestClient, agent: TurnAgent) -> None:
    start(client, new_id(), disabled_tools=["tool_calc"])
    wait_until(lambda: agent.asks)
    assert agent.asks[0]["disabled_tools"] == []


@pytest.mark.parametrize("stored", [{"max_tool_rounds": 4, "max_output_tokens": True}])
def test_only_whole_number_limits_reach_the_agent(client: TestClient, agent: TurnAgent, stored) -> None:
    client.portal.call(client.app.state.store.put, "tuning_limits", "u-1", {"owner": "u-1", **stored})
    start(client, new_id())
    wait_until(lambda: agent.asks)
    assert agent.asks[0]["limits"] == {"max_tool_rounds": 4}


def test_unreadable_limits_keep_the_turn_running(client: TestClient, db_gateway, agent: TurnAgent) -> None:
    fail_collection(db_gateway, "tuning_limits")
    chat_id = new_id()
    assert start(client, chat_id).status_code == 202
    events(client, chat_id)
    assert not agent.asks[-1]["limits"]


# --- usage ------------------------------------------------------------------------------


def test_a_turn_still_answers_when_its_usage_cannot_be_recorded(client: TestClient, db_gateway, agent: TurnAgent) -> None:
    real = db_gateway.put

    async def selective(collection, key, doc):
        if collection == "usage_records":
            raise DbGatewayError("down")
        return await real(collection, key, doc)

    db_gateway.put = selective
    chat_id = new_id()
    start(client, chat_id)
    assert events(client, chat_id)[-1]["type"] == "final"
    assert chat(client, chat_id)["messages"][-1]["content"] == "Hello!"


def test_a_turn_is_refused_when_the_limit_cannot_be_checked(client: TestClient, db_gateway, agent: TurnAgent) -> None:
    fail_collection(db_gateway, "usage_records")
    assert start(client, new_id()).status_code == 503
    assert agent.asks == []


def test_a_suggestion_is_skipped_when_the_limit_cannot_be_checked(client: TestClient, db_gateway, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id, "What is the capital of France?")
    events(client, chat_id)
    fail_collection(db_gateway, "usage_records")
    assert client.get(f"/turns/{chat_id}/suggestion").json() == {"text": None}
    assert agent.interprets == []


# --- the chat trace ------------------------------------------------------------------------


def test_chat_turns_are_traced_and_agent_failures_logged(client: TestClient, agent: TurnAgent, platform) -> None:
    chat_id = new_id()
    start(client, chat_id, "What is up?", trusted={"extension_ids": ["notes"]})
    events(client, chat_id)
    wait_until(lambda: traces(platform))
    (trace,) = traces(platform)
    assert trace["message"].startswith(f"What is up? → {AGENT_ID}/claude-test, ")
    assert '"enabled_extensions": [\n    "notes"\n  ]' in trace["details"] and '"response": "Hello!"' in trace["details"]

    agent.fail = "provider rate limited"
    other = new_id()
    start(client, other)
    events(client, other)
    wait_until(lambda: any(line["kind"] == "error" for line in platform.logs))
    assert [line["message"] for line in platform.logs if line["kind"] == "error"] == [f"{AGENT_ID}: provider rate limited"]


def test_chat_trace_lists_each_agent_and_keeps_the_prompts_apart(client: TestClient, agent: TurnAgent, platform) -> None:
    agent.result_extra = {"agent_usage": TRACE_ROWS}
    agent.tool_calls = ["notes"]
    chat_id = new_id()
    start(client, chat_id, "add 2 and 3")
    events(client, chat_id)
    wait_until(lambda: traces(platform))
    trace = traces(platform)[0]
    details = json.loads(trace["details"])
    assert [a["agent_id"] for a in details["agents"]] == ["claude-agent", "calc"]
    first, second = details["agents"]
    assert (first["model_tier"], first["reasoning_effort"], first.get("delegated_by")) == ("heavy", "low", None)
    assert second["delegated_by"] == "claude-agent"
    assert first["tools"] == ["notes"] and second["tools"] == []
    assert "prompt" not in first and "earlier" not in trace["details"]
    prompts = json.loads(trace["prompts"])
    assert [p["messages"][-1]["content"] for p in prompts] == ["add 2 and 3", "2 + 3"]
    assert prompts[0]["truncated"] is False


def test_chat_trace_prompts_are_clipped_to_a_budget_keeping_the_newest(client: TestClient, agent: TurnAgent, platform) -> None:
    big = [{"role": "user", "content": "old " * 5000}, {"role": "user", "content": "the question"}]
    agent.result_extra = {"agent_usage": [{**TRACE_ROWS[0], "prompt": big}]}
    chat_id = new_id()
    start(client, chat_id, "x")
    events(client, chat_id)
    wait_until(lambda: traces(platform))
    prompt = json.loads(traces(platform)[0]["prompts"])[0]
    assert prompt["truncated"] is True
    assert prompt["messages"][-1]["content"] == "the question"
    assert sum(len(m["content"]) for m in prompt["messages"]) <= 12_000
