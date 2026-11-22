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
    def fake_identity(username, email, uid, **kw):
        seen["identity"] = (username, email, uid)
        return {"X-Citadel-Requester": f"token-for-{uid}"}

    monkeypatch.setattr(legion_ask, "identity_headers", fake_identity)
    return seen


def ask(url, question, history, memory=False):
    return asyncio.run(LegionAsk().ask(url, FakeClient(), question, history, memory=memory))


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
    # ":" is not allowed in account usernames, so no account can share this requester name
    assert seen["identity"] == ("outside:oc_abc123def456", "", "oc_abc123def456")


def test_tokens_fall_back_to_the_total_and_then_to_zero(monkeypatch):
    patch(monkeypatch, FakeSession(FakeResult({"response": "x", "total_tokens": 7})))
    assert ask("u", "q", []).tokens == 7
    patch(monkeypatch, FakeSession(FakeResult({"response": "x"})))
    assert ask("u", "q", []).tokens == 0


def test_a_negative_token_count_never_reduces_the_spend(monkeypatch):
    patch(monkeypatch, FakeSession(FakeResult({"response": "x", "agent_usage": [{"total_tokens": -50}, {"total_tokens": 10}]})))
    assert ask("u", "q", []).tokens == 10
    patch(monkeypatch, FakeSession(FakeResult({"response": "x", "total_tokens": -9})))
    assert ask("u", "q", []).tokens == 0


@pytest.mark.parametrize("session", [
    FakeSession(raises=RuntimeError("down")), FakeSession(FakeResult({}, error=True)),
    FakeSession(FakeResult({"response": "  "})), FakeSession(FakeResult(None)),
    FakeSession(FakeResult({"response": "⏹️ Cancelled.", "cancelled": True})),
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


def probe(disabled_tools, extra=()):
    """Legion's real recall, skill recall, skill learning and call_tool, with a recording fake upstream."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "AI_AGENT_FILE": str(LEGION / "agents/ember.json")}
    done = subprocess.run([str(LEGION_PYTHON), "-B", str(Path(__file__).with_name("legion_filter_probe.py"))], cwd=LEGION,
                          input=json.dumps({"disabled": disabled_tools, "extra": list(extra)} if extra else disabled_tools), capture_output=True, text=True, timeout=120, env=env)
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


@pytest.mark.skipif(LEGION_PYTHON is None, reason="Legion's virtual environment is not installed")
def test_legion_lets_only_the_five_brain_tools_through_the_stronghold_level_filter(monkeypatch):
    session = FakeSession(FakeResult({"response": "x"}))
    patch(monkeypatch, session)
    ask("u", "q", [], memory=True)
    sent = session.calls[0][1]["disabled_tools"]
    allowed = set(legion_ask.STRONGHOLD_ALLOWED)
    others = ["stronghold__tool_brain_propose", "stronghold__tool_ticket_createTicket",
              "stronghold__tool_usage_summary", "armory__tool_web_search"]

    result = probe(sent, others + sorted(allowed))
    assert set(result["upstream_calls"]) == allowed
    assert all(result["direct"][name] == "PermissionError" for name in others)
    assert all(result["direct"][name] == "ran" for name in allowed)
    assert result["direct"]["stronghold__tool_skill_search"] == "PermissionError"
    assert result["direct"]["stronghold__tool_skill_propose"] == "PermissionError"
    assert result["skills_unchanged"] and result["proposed"] is False
