"""LegionAsk: one stateless ask call to the entry agent as the outside client."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.services import legion_ask
from src.services.legion_ask import LegionAsk, LegionUnavailable


class FakeClient:
    uid, name = "oc_abc123def456", "bot"


class FakeResult:
    def __init__(self, data, error=False):
        self.structuredContent, self.isError, self.content = data, error, []


class FakeSession:
    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.calls = result, raises, []

    async def call_tool(self, name, arguments, **kwargs):
        self.calls.append((name, arguments))
        if self.raises:
            raise self.raises
        return self.result


def patch(monkeypatch, session):
    seen = {}

    class Context:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *exc):
            return False

    def fake_session(url, headers, timeout):
        seen["url"], seen["headers"] = url, headers
        return Context()

    monkeypatch.setattr(legion_ask, "mcp_session", fake_session)
    monkeypatch.setattr(legion_ask, "identity_headers", lambda username, email, uid, **kw: {"X-Citadel-Requester": f"token-for-{uid}"})
    return seen


def ask(url, question, history):
    return asyncio.run(LegionAsk().ask(url, FakeClient(), question, history))


def test_the_call_is_stateless_and_carries_the_clients_identity(monkeypatch):
    session = FakeSession(FakeResult({"response": "Hello!", "agent_usage": [{"total_tokens": 30}, {"total_tokens": 12}]}))
    seen = patch(monkeypatch, session)
    answer = ask("http://legion/mcp", "Hi", [{"role": "user", "content": "earlier"}])
    name, arguments = session.calls[0]
    assert name == "ask" and arguments["question"] == "Hi" and arguments["history"] == [{"role": "user", "content": "earlier"}]
    assert arguments["enabled_extensions"] == [] and arguments["approval_mode"] == "deny" and arguments["allowed_tools"] == []
    assert arguments["plan"] is False and arguments["ask_user"] is False and not arguments.get("private_extensions")
    assert arguments["disabled_tools"] == ["*"] and "plan_lean" not in arguments and "depth" not in arguments
    assert arguments["request_id"] == answer.request_id and answer.request_id
    assert seen["url"] == "http://legion/mcp" and seen["headers"]["X-Citadel-Requester"] == "token-for-oc_abc123def456"
    assert (answer.text, answer.tokens) == ("Hello!", 42)


def test_tokens_fall_back_to_the_total_and_then_to_zero(monkeypatch):
    patch(monkeypatch, FakeSession(FakeResult({"response": "x", "total_tokens": 7})))
    assert ask("u", "q", []).tokens == 7
    patch(monkeypatch, FakeSession(FakeResult({"response": "x"})))
    assert ask("u", "q", []).tokens == 0


@pytest.mark.parametrize("session", [
    FakeSession(raises=RuntimeError("down")), FakeSession(FakeResult({}, error=True)),
    FakeSession(FakeResult({"response": "  "})), FakeSession(FakeResult(None)),
])
def test_any_failure_or_empty_answer_is_unavailable(monkeypatch, session):
    patch(monkeypatch, session)
    with pytest.raises(LegionUnavailable) as caught:
        ask("u", "secret question text", [])
    assert "secret question text" not in str(caught.value)


LEGION = Path(__file__).resolve().parents[2] / "legion"
APPS = Path(sys.executable).resolve().parents[3]  # .../apps/portcullis/.venv/Scripts/python.exe
LEGION_PYTHON = next((p for p in (APPS / "legion/.venv/Scripts/python.exe", APPS / "legion/.venv/bin/python",
                                  LEGION / ".venv/Scripts/python.exe", LEGION / ".venv/bin/python") if p.exists()), None)


def probe(disabled_tools):
    """Legion's real recall, skill recall, skill learning and call_tool, with a recording fake upstream."""
    env = {**os.environ, "AI_AGENT_FILE": str(LEGION / "agents/ember.json")}
    done = subprocess.run([str(LEGION_PYTHON), str(Path(__file__).with_name("legion_filter_probe.py"))], cwd=LEGION,
                          input=json.dumps(disabled_tools), capture_output=True, text=True, timeout=120, env=env)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(LEGION_PYTHON is None, reason="Legion's virtual environment is not installed")
def test_legion_refuses_every_tool_the_outside_ask_could_reach(monkeypatch):
    session = FakeSession(FakeResult({"response": "x"}))
    patch(monkeypatch, session)
    ask("u", "q", [])
    sent = session.calls[0][1]["disabled_tools"]

    control = probe([])  # the hole as it was: recall, skill search and skill propose reach the upstream
    assert {"stronghold__tool_brain_search", "stronghold__tool_skill_search",
            "stronghold__tool_skill_propose"} <= set(control["upstream_calls"])

    result = probe(sent)
    assert result["upstream_calls"] == []
    assert set(result["direct"].values()) == {"PermissionError"} and len(result["direct"]) == 4
    assert result["recall_unchanged"] and result["skills_unchanged"] and result["proposed"] is False
