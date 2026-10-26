"""'Auto' approval: with allow_read_only a built-in tool that declares readOnlyHint runs without
asking, and everything else asks as before (approvals.py, mcp_upstream.py, agent_config.py, server.py)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src import server
from src.runtime import approvals
from src.providers import cancellation
from src.providers.base_provider import ChatResult
from src.tools.mcp_client import mcp_upstream

REQUEST = "req-ro"
READ = "main__tool_notes_listNotes"
WRITE = "main__tool_notes_createNote"
EXTENSION = "main__pdf_merger__tool_read"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    cancellation.clear(REQUEST)
    monkeypatch.setattr(approvals, "BROKER", approvals.ApprovalBroker(timeout=3.0, poll=0.05))
    yield
    cancellation.clear(REQUEST)


def tool(name: str, read_only):
    annotations = None if read_only is None else SimpleNamespace(readOnlyHint=read_only)
    return SimpleNamespace(name=name, annotations=annotations)


def only_reads(names=(READ,)):
    return lambda name: name in names


class Recorder:
    """Collects events; answers an approval_request with `decision` at once."""

    def __init__(self, decision: str = "allow") -> None:
        self.events: list[dict] = []
        self._decision = decision

    async def __call__(self, event: dict) -> None:
        self.events.append(event)
        if event["type"] == "approval_request":
            # On the next loop turn, after the waiter has registered.
            asyncio.get_running_loop().call_soon(approvals.BROKER.decide, REQUEST, event["id"], self._decision)

    def asked(self) -> list[str]:
        return [e["tool"] for e in self.events if e["type"] == "approval_request"]


def review(recorder, name, step_id="s1"):
    return approvals.review(REQUEST, step_id, name, None, {}, recorder)


def under(policy, factory):
    async def scenario():
        token = approvals.bind(policy)
        try:
            return await factory()
        finally:
            approvals.reset(token)

    return run(scenario())


# ---- the policy ----


def test_a_read_only_tool_needs_no_approval_in_ask_mode_when_checked():
    policy = approvals.ApprovalPolicy("ask", read_only_check=only_reads())

    assert policy.needs_approval(READ) is False
    assert policy.needs_approval(WRITE) is True


def test_without_a_check_every_tool_still_asks():
    assert approvals.ApprovalPolicy("ask").needs_approval(READ) is True


def test_deny_and_off_modes_ignore_the_check():
    assert approvals.ApprovalPolicy("deny", read_only_check=only_reads()).needs_approval(READ) is True  # a delegate cannot ask
    assert approvals.ApprovalPolicy("off", read_only_check=only_reads()).needs_approval(READ) is False
    assert approvals.ApprovalPolicy("off", read_only_check=only_reads()).needs_approval(WRITE) is False


def test_a_private_tool_always_asks_even_if_the_check_says_read_only():
    policy = approvals.ApprovalPolicy("ask", ask_prefixes=("u_",), read_only_check=lambda name: True)

    assert policy.needs_approval("u_notes__read") is True
    assert policy.needs_approval(READ) is False


def test_once_a_private_tool_ran_everything_asks_again():
    policy = approvals.ApprovalPolicy("ask", read_only_check=only_reads())
    assert policy.needs_approval(READ) is False

    policy.tainted = True

    assert policy.needs_approval(READ) is True
    assert approvals.ApprovalPolicy("ask", {READ}, read_only_check=only_reads(), tainted=True).needs_approval(READ) is False  # allowed for the chat


def test_a_tool_allowed_for_the_chat_still_runs_without_asking():
    assert approvals.ApprovalPolicy("ask", {WRITE}, read_only_check=only_reads()).needs_approval(WRITE) is False


# ---- review ----


def test_review_runs_a_read_only_tool_without_a_word_and_asks_for_a_write():
    rec = Recorder("allow")
    policy = approvals.ApprovalPolicy("ask", read_only_check=only_reads())

    async def both():
        return await review(rec, READ, "s1"), await review(rec, WRITE, "s2")

    assert under(policy, both) == (None, None)
    assert rec.asked() == [WRITE]


def test_review_still_refuses_a_denied_write_in_auto():
    rec = Recorder("deny")

    outcome = under(approvals.ApprovalPolicy("ask", read_only_check=only_reads()), lambda: review(rec, WRITE))

    assert outcome == approvals.DECLINED


# ---- which tools count as read-only ----


def test_only_built_in_tools_that_declare_read_only_count(monkeypatch):
    listed = [
        tool(READ, True),
        tool(WRITE, False),  # declares it changes things
        tool("main__tool_x_noHint", None),  # declares nothing: asks
        tool(EXTENSION, True),  # an extension's tool may not vouch for itself
        tool("other__tool", True),  # not from the mcp_server upstream
    ]
    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: listed)

    mcp_upstream.list_tools()

    assert mcp_upstream.is_read_only_builtin(READ) is True
    for name in (WRITE, "main__tool_x_noHint", EXTENSION, "other__tool", "u_x__read", "never_listed"):
        assert mcp_upstream.is_read_only_builtin(name) is False, name


def test_the_set_follows_the_latest_listing(monkeypatch):
    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: [tool(READ, True)])
    mcp_upstream.list_tools()
    assert mcp_upstream.is_read_only_builtin(READ) is True

    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: [tool(READ, False)])
    mcp_upstream.list_tools()

    assert mcp_upstream.is_read_only_builtin(READ) is False


def test_a_tool_the_agent_is_not_scoped_to_is_still_known_as_read_only(monkeypatch):
    # The set comes from the raw listing, before scoping, so it never depends on one agent's globs.
    monkeypatch.setattr(mcp_upstream.client, "list_tools", lambda: [tool(READ, True)])
    monkeypatch.setattr(mcp_upstream.tool_filter, "is_blocked", lambda name: True)  # switched off for this user

    assert mcp_upstream.list_tools() == []
    assert mcp_upstream.is_read_only_builtin(READ) is True  # offering is decided elsewhere; this only classifies


# ---- the turn ----


def _result() -> ChatResult:
    return ChatResult(response="ok", provider_id="anthropic", model="m", total_tokens=1)


def test_run_chat_binds_the_check_only_for_ask_mode_with_the_option_on():
    from src.agents import agent_config

    seen: list[approvals.ApprovalPolicy] = []

    async def fake_provider_run_chat(*args, **kwargs):
        seen.append(approvals.current())
        return _result()

    with patch.object(agent_config._PROVIDER_MODULE, "run_chat", fake_provider_run_chat):
        for mode, allow in (("ask", True), ("ask", False), ("off", True), ("deny", True)):
            run(agent_config.run_chat("q", [], [], request_id=REQUEST, approval_mode=mode, allow_read_only=allow))

    has_check = [policy.read_only_check is not None for policy in seen]
    assert has_check == [True, False, False, False]
    assert seen[0].read_only_check is mcp_upstream.is_read_only_builtin


def test_a_laya_model_has_no_check(monkeypatch):
    from src.agents import agent_config

    monkeypatch.setattr(agent_config, "PROVIDER_ID", "decision")

    assert agent_config._read_only_check() is None


def test_ask_passes_allow_read_only_on_and_defaults_it_off():
    async def call(**kwargs):
        with patch("src.server.agent_config.run_chat", new_callable=AsyncMock, return_value=_result()) as run_chat, \
             patch("src.server.agent_config.status", return_value={"context_window": 1, "model": "m"}):
            await server.ask("q", request_id="r", approval_mode="ask", **kwargs)
        return run_chat.call_args.kwargs

    assert run(call())["allow_read_only"] is False
    assert run(call(allow_read_only=True))["allow_read_only"] is True


def test_status_says_the_agent_understands_it():
    assert server.status()["read_only_approval"] is True
