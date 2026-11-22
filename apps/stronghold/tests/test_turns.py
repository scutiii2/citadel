"""/turns: a chat turn run by Stronghold, from start to the saved answer (ported from Portcullis's turn tests)."""

from __future__ import annotations
from tests.auth_helpers import identity, IdentityHeaders

import json
import re
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import AGENTS, IDENTITY
from tests.turn_agent import TurnAgent
from src.usage.settings import UsageSettings

AGENT_ID = AGENTS[0]["id"]
OTHER = IdentityHeaders(uid="u-2", username="bob")
MESSAGE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@pytest.fixture
def agent() -> TurnAgent:
    return TurnAgent()


def new_id() -> str:
    return str(uuid.uuid4())


def start(client: TestClient, chat_id: str, question: str = "hi there", trusted: dict | None = None, **extra):
    """Portcullis's trusted block defaults here to "asking is up to the browser, tools allowed"."""
    body = {"question": question, "trusted": {"forced_approval": False, "tools_execute": True, **(trusted or {})}, **extra}
    return client.post(f"/turns/{chat_id}", json=body)


def events(client: TestClient, chat_id: str, after: int = 0, headers: dict | None = None) -> list[dict]:
    with client.stream("GET", f"/turns/{chat_id}/events", params={"after": after}, headers=headers) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b"".join(response.iter_bytes()).decode()
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def streamed_text(stream: list[dict]) -> str:
    return "".join(e.get("text", "") for e in stream if e["type"] in ("snapshot", "token"))


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def chat(client: TestClient, chat_id: str) -> dict:
    return client.get(f"/chats/{chat_id}").json()


def running(client: TestClient) -> list[str]:
    return client.get("/turns/running").json()["chat_ids"]


# --- a whole turn ------------------------------------------------------------------


def test_a_turn_creates_the_chat_answers_and_saves(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    response = start(client, chat_id, "What is up?", caveman=True)

    assert response.status_code == 202
    assert response.json()["chat"]["title"] == "What is up?" and response.json()["chat"]["running"] is True
    stream = events(client, chat_id)
    assert stream[-1]["type"] == "final" and streamed_text(stream) == "Hello!"
    saved = chat(client, chat_id)
    assert saved["agent_id"] == AGENT_ID
    answer = saved["messages"][1]
    assert 0 <= answer.pop("duration_s") < 60
    asked_at, answered_at = (m.pop("at") for m in saved["messages"])
    assert MESSAGE_TIME.match(asked_at) and MESSAGE_TIME.match(answered_at) and asked_at <= answered_at
    assert saved["messages"] == [
        {"role": "user", "content": "What is up?"},
        {"role": "assistant", "content": "Hello!", "agent": AGENT_ID, "model": "claude-test", "total_tokens": 100,
         "input_tokens": 70, "output_tokens": 30, "context_tokens": 1000, "context_window": 200000},
    ]
    asked = agent.asks[0]
    assert (asked["question"], asked["history"], asked["caveman"]) == ("What is up?", [], True)
    assert asked["url"] == AGENTS[0]["url"] and asked["caller"].username == "ana"


def test_the_second_turn_sends_history_without_raw_logs(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id, "first")
    events(client, chat_id)
    start(client, chat_id, "second")
    events(client, chat_id)
    assert [m["role"] for m in chat(client, chat_id)["messages"]] == ["user", "assistant", "user", "assistant"]
    assert agent.asks[1]["history"] == [{"role": "user", "content": "first"}, {"role": "assistant", "content": "Hello!"}]


def test_independent_sends_no_history(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id, "first")
    events(client, chat_id)
    start(client, chat_id, "alone", independent=True)
    events(client, chat_id)
    assert agent.asks[1]["history"] == [] and len(chat(client, chat_id)["messages"]) == 4


def test_truncate_to_replaces_a_question_and_what_followed(client: TestClient, agent: TurnAgent) -> None:
    chat_id = new_id()
    start(client, chat_id, "one")
    events(client, chat_id)
    start(client, chat_id, "two")
    events(client, chat_id)
    assert start(client, chat_id, "two again", truncate_to=2).status_code == 202
    events(client, chat_id)
    assert [m["content"] for m in chat(client, chat_id)["messages"]] == ["one", "Hello!", "two again", "Hello!"]


@pytest.mark.parametrize("index", [1, 9])
def test_truncate_to_must_point_at_a_typed_question(client: TestClient, agent: TurnAgent, index: int) -> None:
    chat_id = new_id()
    start(client, chat_id, "one")
    events(client, chat_id)
    assert start(client, chat_id, "x", truncate_to=index).status_code == 422
    assert start(client, new_id(), "x", truncate_to=0).status_code == 404


def test_a_failed_agent_call_is_saved_and_streamed(client: TestClient, agent: TurnAgent, platform) -> None:
    agent.fail = "agent down"
    chat_id = new_id()
    start(client, chat_id)
    stream = events(client, chat_id)
    assert stream[-1] == {"type": "error", "message": "agent down", "sequence": stream[-1]["sequence"]}
    assert chat(client, chat_id)["messages"][-1]["content"] == "error: agent down"
    assert any(line["kind"] == "error" and line["source"] == "chat.answer" and line["uid"] == "u-1" for line in platform.logs)


def test_no_agent_running_is_503(client: TestClient, tmp_path) -> None:
    (tmp_path / "config_agents.json").write_text(json.dumps({"agents": []}), encoding="utf-8")
    assert start(client, new_id()).status_code == 503


def test_the_chat_trace_is_logged_to_portcullis(client: TestClient, platform) -> None:
    chat_id = new_id()
    start(client, chat_id, "trace me")
    events(client, chat_id)
    wait_until(lambda: any(line["kind"] == "chat_trace" for line in platform.logs))
    line = next(line for line in platform.logs if line["kind"] == "chat_trace")
    assert line["uid"] == "u-1" and line["source"] == "chat.turn" and "trace me" in line["message"]


# --- watching, busy, cancel, discard ------------------------------------------------


def test_a_running_turn_blocks_a_second_one_and_is_listed(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.asks)
    assert running(client) == [chat_id]
    assert start(client, chat_id).status_code == 409
    agent.release()
    events(client, chat_id)
    assert running(client) == []


def test_three_turns_run_at_most_per_account(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    ids = [new_id() for _ in range(4)]
    for chat_id in ids[:3]:
        assert start(client, chat_id).status_code == 202
    assert start(client, ids[3]).status_code == 429
    for chat_id in ids[:3]:
        client.post(f"/turns/{chat_id}/cancel")


def test_a_late_subscriber_gets_a_snapshot_then_the_rest(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    agent.events = [{"type": "token", "text": "Hel"}]
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.gate is not None)
    # TestClient hands over a streamed body only once it is complete, so the turn is let go from another thread.
    timer = threading.Timer(0.3, agent.release)
    timer.start()
    stream = events(client, chat_id)
    timer.join()
    assert (stream[0]["type"], stream[0]["text"]) == ("snapshot", "Hel")
    assert stream[-1]["type"] == "final" and not any(e["type"] == "token" for e in stream[1:])


def test_tool_steps_are_saved_on_the_answer(client: TestClient, agent: TurnAgent) -> None:
    agent.tool_calls = ["web_search"]
    chat_id = new_id()
    start(client, chat_id, trusted={"forced_approval": False})
    events(client, chat_id)
    steps = chat(client, chat_id)["messages"][1]["steps"]
    assert steps == [{"tool": "web_search", "label": "WEB_SEARCH", "arguments": {"a": 1}, "ok": True, "result": "done"}]


def test_cancel_keeps_what_streamed(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.gate is not None)
    assert client.post(f"/turns/{chat_id}/cancel").json() == {"cancelled": True}
    stream = events(client, chat_id)
    assert stream[-1]["type"] == "final" and stream[-1]["cancelled"] is True
    assert chat(client, chat_id)["messages"][1]["content"].startswith("Hello!")
    assert client.post(f"/turns/{chat_id}/cancel").json() == {"cancelled": False}


def test_discarding_a_running_chat_stops_it(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.gate is not None)
    assert client.delete(f"/turns/{chat_id}").status_code == 204
    wait_until(lambda: running(client) == [])
    assert client.get(f"/turns/{chat_id}/events").status_code == 404


def test_turns_are_private_to_their_account(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.gate is not None)
    assert client.get(f"/turns/{chat_id}/events", headers=identity(uid="u-2", username="bob")).status_code == 404
    assert client.post(f"/turns/{chat_id}/cancel", headers=identity(uid="u-2", username="bob")).json() == {"cancelled": False}
    assert client.get("/turns/running", headers=identity(uid="u-2", username="bob")).json() == {"chat_ids": []}
    agent.release()
    events(client, chat_id)


def test_no_turn_to_watch_is_404(client: TestClient) -> None:
    assert client.get(f"/turns/{new_id()}/events").status_code == 404


def test_discard_account_stops_all_its_turns(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    start(client, new_id())
    wait_until(lambda: agent.gate is not None)
    assert client.delete("/turns/accounts/u-1").status_code == 204
    wait_until(lambda: running(client) == [])


# --- what Portcullis decides --------------------------------------------------------


def test_the_trusted_block_sets_extensions_and_tool_approval(client: TestClient, agent: TurnAgent) -> None:
    start(client, new_id(), trusted={"forced_approval": False, "tools_execute": True},
          ask_before_tools=True, allowed_tools=["a", "a", "b"], allow_read_only=True)
    wait_until(lambda: agent.asks)
    asked = agent.asks[0]
    assert "enabled_extensions" not in asked and asked["approval_mode"] == "ask"
    assert asked["allowed_tools"] == ["a", "b"] and asked["allow_read_only"] is True and asked["disabled_tools"] == []


def test_forced_approval_overrides_the_browsers_choice(client: TestClient, agent: TurnAgent) -> None:
    start(client, new_id(), trusted={"forced_approval": True, "tools_execute": True}, allowed_tools=["a"], allow_read_only=True)
    wait_until(lambda: agent.asks)
    asked = agent.asks[0]
    assert asked["approval_mode"] == "ask" and asked["allowed_tools"] == [] and asked["allow_read_only"] is False


def test_an_account_without_tools_execute_gets_no_tools(client: TestClient, agent: TurnAgent) -> None:
    start(client, new_id(), trusted={"forced_approval": False, "tools_execute": False})
    wait_until(lambda: agent.asks)
    assert agent.asks[0]["disabled_tools"] == ["*"]


def test_switched_off_agents_are_left_out(client: TestClient, agent: TurnAgent) -> None:
    assert client.put("/account-agents/openai-agent", json={"enabled": False}).status_code == 200
    start(client, new_id(), trusted={"forced_approval": False, "tools_execute": True})
    wait_until(lambda: agent.asks)
    assert agent.asks[0]["disabled_tools"] == ["agent:openai-agent"]


def test_private_extensions_reach_the_agent(client: TestClient, agent: TurnAgent) -> None:
    saved = client.post("/user-extensions", json={"label": "Mine", "url": "https://mcp.example.com/mcp",
                                                  "headers": {"Authorization": "Bearer x"}})
    assert saved.status_code == 201
    start(client, new_id())
    wait_until(lambda: agent.asks)
    sent = agent.asks[0]["private_extensions"]
    assert [e["label"] for e in sent] == ["Mine"] and sent[0]["headers"] == {"Authorization": "Bearer x"}


def test_the_account_limits_reach_the_agent(client: TestClient, agent: TurnAgent) -> None:
    client.portal.call(client.app.state.limits.replace, "u-1", {"max_output_tokens": 500, "max_tool_rounds": None})
    start(client, new_id())
    wait_until(lambda: agent.asks)
    assert agent.asks[0]["limits"] == {"max_output_tokens": 500}



# --- approvals and questions -----------------------------------------------------------


def test_a_tool_waits_for_approval_and_runs_once_allowed(client: TestClient, agent: TurnAgent) -> None:
    agent.tool_calls = ["send_mail"]
    chat_id = new_id()
    start(client, chat_id, trusted={"forced_approval": True})
    wait_until(lambda: client.app.state.turns.pending_approval("u-1", chat_id, "step0") is not None)
    answered = client.post(f"/turns/{chat_id}/approvals", json={"step_id": "step0", "decision": "always", "trusted": {"forced_approval": True}})
    assert answered.json() == {"decided": True, "decision": "allow", "tool": "send_mail"}
    events(client, chat_id)
    assert agent.ran == ["send_mail"] and agent.decisions[0][2] == "allow"


def test_an_approval_with_nothing_waiting_is_refused(client: TestClient, agent: TurnAgent) -> None:
    body = {"step_id": "step0", "decision": "allow"}
    assert client.post(f"/turns/{new_id()}/approvals", json=body).status_code == 404
    agent.hold = True
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.gate is not None)
    assert client.post(f"/turns/{chat_id}/approvals", json=body).status_code == 409
    agent.release()
    events(client, chat_id)


def test_an_agent_failure_while_deciding_is_502(client: TestClient, agent: TurnAgent) -> None:
    agent.tool_calls = ["x"]
    agent.decide_error = "agent gone"
    chat_id = new_id()
    start(client, chat_id, ask_before_tools=True)
    wait_until(lambda: client.app.state.turns.pending_approval("u-1", chat_id, "step0") is not None)
    assert client.post(f"/turns/{chat_id}/approvals", json={"step_id": "step0", "decision": "allow"}).status_code == 502
    client.post(f"/turns/{chat_id}/cancel")
    events(client, chat_id)


QUESTIONS = [{"header": "Format", "question": "Which format?", "multi_select": False,
              "options": [{"label": "CSV"}, {"label": "JSON"}]}]


def test_a_question_is_answered_and_the_turn_goes_on(client: TestClient, agent: TurnAgent) -> None:
    agent.questions = QUESTIONS
    chat_id = new_id()
    start(client, chat_id, can_ask=True)
    wait_until(lambda: client.app.state.turns.pending_question("u-1", chat_id, "q1") is not None)
    bad = client.post(f"/turns/{chat_id}/questions", json={"step_id": "q1", "answers": [{"selected": ["XML"]}]})
    assert bad.status_code == 422
    ok = client.post(f"/turns/{chat_id}/questions", json={"step_id": "q1", "answers": [{"selected": ["CSV"]}]})
    assert ok.json() == {"answered": True}
    assert events(client, chat_id)[-1]["type"] == "final"
    assert agent.asks[0]["ask_user"] is True


def test_skipping_a_question_needs_no_answers(client: TestClient, agent: TurnAgent) -> None:
    agent.questions = QUESTIONS
    chat_id = new_id()
    start(client, chat_id, can_ask=True)
    wait_until(lambda: client.app.state.turns.pending_question("u-1", chat_id, "q1") is not None)
    assert client.post(f"/turns/{chat_id}/questions", json={"step_id": "q1", "skipped": True}).json() == {"answered": True}
    events(client, chat_id)
    assert agent.answers[0][3] is True


# --- usage ---------------------------------------------------------------------------


def test_usage_is_recorded_for_the_turn(client: TestClient) -> None:
    chat_id = new_id()
    start(client, chat_id)
    events(client, chat_id)
    records = client.get("/usage/records").json()
    assert [(r["kind"], r["total_tokens"], r["chat_id"]) for r in records] == [("chat", 100, chat_id)]


def test_the_usage_limit_blocks_a_new_turn(make_client, agent: TurnAgent) -> None:
    client = make_client(usage=UsageSettings(six_hour_token_limit=100))
    first = new_id()
    start(client, first)
    events(client, first)
    blocked = start(client, new_id())
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


# --- summarize, clear, suggestion --------------------------------------------------------------


def add_summarizer(tmp_path) -> None:
    helper = {"id": "context-summarizer", "label": "Context Summarizer", "url": "http://summarizer.internal/mcp"}
    (tmp_path / "config_agents.json").write_text(json.dumps({"agents": [*AGENTS, helper]}), encoding="utf-8")


@pytest.fixture
def summarizer(tmp_path):
    add_summarizer(tmp_path)


def two_turns(client: TestClient) -> str:
    chat_id = new_id()
    for question in ("first", "second"):
        start(client, chat_id, question)
        events(client, chat_id)
    return chat_id


def test_manual_summarize_replaces_the_history(client: TestClient, agent: TurnAgent, summarizer) -> None:
    chat_id = two_turns(client)
    done = client.post(f"/turns/{chat_id}/summarize")
    assert done.status_code == 200
    kinds = [m.get("kind") for m in done.json()["messages"]]
    assert kinds == ["summary", "log_attachment"] and done.json()["messages"][0]["content"] == "SUMMARY"
    assert chat(client, chat_id)["messages"] == [{k: v for k, v in m.items() if k != "cost"} for m in done.json()["messages"]]


def test_summarize_needs_the_summarizer_and_a_idle_chat(client: TestClient, agent: TurnAgent) -> None:
    chat_id = two_turns(client)
    assert client.post(f"/turns/{chat_id}/summarize").status_code == 503
    assert client.post(f"/turns/{new_id()}/summarize").status_code == 404


def test_a_failed_summarize_changes_nothing(client: TestClient, agent: TurnAgent, summarizer) -> None:
    chat_id = two_turns(client)
    before = chat(client, chat_id)["messages"]
    agent.fail = "model down"
    assert client.post(f"/turns/{chat_id}/summarize").status_code == 502
    assert chat(client, chat_id)["messages"] == before


def test_clear_keeps_one_raw_log(client: TestClient, agent: TurnAgent) -> None:
    chat_id = two_turns(client)
    done = client.post(f"/turns/{chat_id}/clear")
    assert [m["kind"] for m in done.json()["messages"]] == ["log_attachment"]
    assert "first" in done.json()["messages"][0]["content"]


def test_auto_summarize_when_the_context_is_nearly_full(make_client, agent: TurnAgent, tmp_path) -> None:
    client = make_client(usage=UsageSettings(max_context_tokens_per_chat=1000, auto_summarize_ratio=0.5))
    add_summarizer(tmp_path)
    chat_id = new_id()
    start(client, chat_id, "first")
    events(client, chat_id)
    start(client, chat_id, "second")
    stream = events(client, chat_id)
    assert [e["type"] for e in stream if e["type"] in ("summarizing", "summarized")] == ["summarizing", "summarized"]
    assert agent.asks[1]["history"][0]["content"] == "SUMMARY"


def test_an_auto_summarize_failure_still_answers(make_client, agent: TurnAgent, tmp_path) -> None:
    client = make_client(usage=UsageSettings(max_context_tokens_per_chat=1000, auto_summarize_ratio=0.5))
    add_summarizer(tmp_path)
    chat_id = new_id()
    start(client, chat_id, "first")
    events(client, chat_id)
    agent.fail = None
    original = agent.interpret

    async def broken(url, caller, text):
        from src.agents.gateway import AgentCallError

        raise AgentCallError("down")

    agent.interpret = broken
    start(client, chat_id, "second")
    assert events(client, chat_id)[-1]["type"] == "final"
    assert agent.asks[1]["history"][0]["content"] == "first"
    agent.interpret = original


def test_the_suggestion_follows_the_last_answer_and_is_asked_once(client: TestClient, agent: TurnAgent) -> None:
    agent.summary = "And what about Germany?"
    chat_id = new_id()
    start(client, chat_id, "What is the capital of France?")
    events(client, chat_id)
    assert client.get(f"/turns/{chat_id}/suggestion").json() == {"text": "And what about Germany?"}
    assert client.get(f"/turns/{chat_id}/suggestion").json() == {"text": "And what about Germany?"}
    assert len(agent.interprets) == 1
    assert sorted(r["kind"] for r in client.get("/usage/records").json()) == ["chat", "suggestion"]
    assert client.get(f"/turns/{new_id()}/suggestion").status_code == 404


def test_shutdown_saves_what_streamed_as_interrupted(client: TestClient, agent: TurnAgent) -> None:
    agent.hold = True
    chat_id = new_id()
    start(client, chat_id)
    wait_until(lambda: agent.gate is not None)
    wait_until(lambda: client.app.state.turns.get("u-1", chat_id).text == "Hello!")
    client.portal.call(client.app.state.turns.shutdown)
    saved = chat(client, chat_id)["messages"][-1]["content"]
    assert saved.startswith("Hello!") and "Interrupted" in saved
    assert client.get("/turns/running").json() == {"chat_ids": []}
