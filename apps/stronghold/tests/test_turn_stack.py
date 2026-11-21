import json

import pytest

from tests.conftest import IDENTITY
from tests.test_chats import A as CHAT, put
from tests.test_turns import add_summarizer, events, start, wait_until


@pytest.fixture
def chat_with_message(client):
    assert put(client, CHAT, messages=[{"role": "user", "content": "earlier question"}]).status_code == 200
    return CHAT


def fill(client, chat_id, count):
    for index in range(count):
        assert client.post(f"/stack/{chat_id}/items", json={"text": f"example item {index}"}).status_code == 201


def run_turn(client, chat_id):
    assert start(client, chat_id).status_code == 202
    assert events(client, chat_id)[-1]["type"] == "final"


def test_a_nearly_full_stack_is_compacted_before_the_agent_is_asked(client, agent, chat_with_message, tmp_path, monkeypatch):
    add_summarizer(tmp_path)
    fill(client, chat_with_message, 33)

    async def ask(url, caller, **kwargs):
        assert len(agent.interprets) == 1
        return {"response": "Answer"}

    monkeypatch.setattr(agent, "ask", ask)
    run_turn(client, chat_with_message)
    view = client.get(f"/stack/{chat_with_message}").json()
    assert [(item["source"], item["text"]) for item in view["items"]] == [("compaction", agent.summary)]
    assert [(row["kind"], row["total_tokens"]) for row in client.get("/usage/records").json()] == [("compaction", 10)]


def test_a_stack_below_the_warning_is_left_alone(client, agent, chat_with_message, tmp_path, monkeypatch):
    add_summarizer(tmp_path)
    fill(client, chat_with_message, 3)

    async def ask(url, caller, **kwargs):
        return {"response": "Answer"}

    monkeypatch.setattr(agent, "ask", ask)
    run_turn(client, chat_with_message)
    assert not agent.interprets
    assert client.get(f"/stack/{chat_with_message}").json()["used"] == 3


def test_a_failed_compaction_never_blocks_the_turn(client, agent, chat_with_message, tmp_path, monkeypatch):
    add_summarizer(tmp_path)
    fill(client, chat_with_message, 33)
    agent.fail = "example summarizer failure"

    async def ask(url, caller, **kwargs):
        assert len(agent.interprets) == 1
        return {"response": "Answer"}

    monkeypatch.setattr(agent, "ask", ask)
    run_turn(client, chat_with_message)
    assert client.get(f"/stack/{chat_with_message}").json()["used"] == 33


def test_the_ask_call_carries_the_chat_id(client, agent, chat_with_message, monkeypatch):
    async def ask(url, caller, **kwargs):
        assert caller.chat_id == chat_with_message
        return {"response": "Answer"}

    monkeypatch.setattr(agent, "ask", ask)
    run_turn(client, chat_with_message)


@pytest.mark.parametrize("tool", [
    "stronghold__tool_stack_list", "stronghold__tool_brain_read", "stronghold__tool_skill_search", "skill_recall", "memory_recall",
    "stronghold__tool_ticket_createTicket", "stronghold__tool_ticket_getTicket",
])
def test_private_tool_text_is_excluded_from_chat_traces(client, agent, chat_with_message, platform, monkeypatch, tool):
    sample = "example remembered fact"

    async def ask(url, caller, **kwargs):
        await kwargs["on_event"]({"type": "step_start", "id": "1", "tool": tool})
        return {
            "response": sample,
            "agent_usage": [{"agent_id": "claude-agent", "prompt": [{"role": "user", "content": sample}]}],
        }

    monkeypatch.setattr(agent, "ask", ask)
    run_turn(client, chat_with_message)
    wait_until(lambda: bool(platform.logs))
    assert sample not in json.dumps(platform.logs)


def test_a_failed_transcript_write_still_ends_a_stack_tool_turn(client, agent, chat_with_message, monkeypatch):
    async def ask(url, caller, **kwargs):
        await kwargs["on_event"]({"type": "step_start", "id": "1", "tool": "stronghold__tool_stack_list"})
        return {"response": "Answer"}

    chats = client.app.state.chats
    replace_messages = chats.replace_messages

    async def fail_after_the_answer(owner, chat_id, messages, **kwargs):
        if messages[-1]["role"] == "assistant":
            raise OSError("example write failure")
        return await replace_messages(owner, chat_id, messages, **kwargs)

    monkeypatch.setattr(agent, "ask", ask)
    monkeypatch.setattr(chats, "replace_messages", fail_after_the_answer)
    assert start(client, chat_with_message).status_code == 202
    turn = client.app.state.turns.get(IDENTITY["uid"], chat_with_message)
    wait_until(turn.task.done)
    assert turn.status == "completed"


def test_a_later_turn_never_logs_stack_text_in_history(client, agent, chat_with_message, platform, monkeypatch):
    sample = "example previous remembered fact"
    calls = 0

    async def ask(url, caller, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            await kwargs["on_event"]({"type": "step_start", "id": "1", "tool": "stronghold__tool_stack_list"})
            return {"response": sample}
        assert any(sample in message["content"] for message in kwargs["history"])
        return {
            "response": "Answer",
            "agent_usage": [{"agent_id": "claude-agent", "prompt": kwargs["history"]}],
        }

    monkeypatch.setattr(agent, "ask", ask)
    run_turn(client, chat_with_message)
    wait_until(lambda: len(platform.logs) >= 1)
    run_turn(client, chat_with_message)
    wait_until(lambda: len(platform.logs) >= 2)
    assert sample not in json.dumps(platform.logs)
