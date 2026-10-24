"""Skill learning: which turns qualify, what the drafting model sees, and that failure is silent."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_registry, delegation, skill_reflection
from src.core import internal_auth
from src.llm.base_provider import ChatResult, ToolCallRecord

DRAFT = {"save": True, "title": "Restart a hung app", "when_to_use": "an app stops responding",
         "steps": "Check its status, stop it, start it again.", "tools": "tool_srv_listApps, tool_srv_stopApp, tool_srv_startApp"}


def call(name, arguments=None, result="ok"):
    return ToolCallRecord(name=name, arguments=arguments if arguments is not None else {"app": "secret-app-01"}, result=result)


def result(*calls, response="Done."):
    return ChatResult(response=response, tool_calls=list(calls))


THREE = (call("main__tool_srv_listApps"), call("main__tool_srv_stopApp"), call("main__tool_srv_startApp"))


def test_a_clean_multi_tool_turn_qualifies_with_names_and_argument_names_only():
    calls = skill_reflection.eligible_calls(result(*THREE))
    assert calls == [("tool_srv_listApps", ["app"]), ("tool_srv_stopApp", ["app"]), ("tool_srv_startApp", ["app"])]


@pytest.mark.parametrize("calls", [THREE[:2], ()])
def test_too_few_tool_calls_do_not_qualify(calls):
    assert skill_reflection.eligible_calls(result(*calls)) is None


def test_bookkeeping_tools_do_not_count_toward_the_minimum():
    extras = (call("main__tool_mem_search"), call("main__tool_skill_search"), call("main__tool_skill_mark"),
              call(delegation.TOOL_NAME), call("update_plan"), call("ask_user"))
    assert skill_reflection.eligible_calls(result(*THREE[:2], *extras)) is None
    assert len(skill_reflection.eligible_calls(result(*THREE, *extras))) == 3


@pytest.mark.parametrize("name", ["main__tool_web_search", "main__tool_firecrawl_scrape", "main__tool_email_send", "u_myext__fetch"])
def test_a_turn_that_touched_untrusted_content_never_qualifies(name):
    assert skill_reflection.eligible_calls(result(*THREE, call(name))) is None


def test_a_turn_with_a_failed_tool_or_no_answer_does_not_qualify():
    failed = call("main__tool_srv_stopApp", result="Tool 'main__tool_srv_stopApp' failed: boom")
    assert skill_reflection.eligible_calls(result(THREE[0], failed, THREE[2])) is None
    assert skill_reflection.eligible_calls(result(*THREE, response="  ")) is None


def test_the_prompt_has_no_results_values_or_answer():
    turn = ChatResult(response="The final answer mentions secret-answer", tool_calls=[
        call("main__tool_srv_listApps", {"app": "secret-app-01"}, result="RESULT-SECRET"), THREE[1], THREE[2]])
    prompt = skill_reflection._prompt("restart my app", skill_reflection.eligible_calls(turn))
    assert "restart my app" in prompt and "tool_srv_listApps(app)" in prompt and "Mode: skill" in prompt
    assert "secret-app-01" not in prompt and "RESULT-SECRET" not in prompt and "secret-answer" not in prompt


def test_a_long_request_is_cut():
    prompt = skill_reflection._prompt("x" * 5000, [("t", [])])
    assert "x" * skill_reflection.REQUEST_CHARS in prompt and "x" * (skill_reflection.REQUEST_CHARS + 1) not in prompt


def test_parse_draft_accepts_a_good_reply_even_with_chatter_around_it():
    assert skill_reflection.parse_draft("Sure!\n" + json.dumps(DRAFT) + "\nDone") == {k: v for k, v in DRAFT.items() if k != "save"}


@pytest.mark.parametrize("text", [
    None, 5, "", "no json here", "{not json", '{"save": false}', '{"save": "yes"}', "[1, 2]",
    json.dumps({**DRAFT, "title": ""}),
    json.dumps({**DRAFT, "title": "x" * 81}),
    json.dumps({**DRAFT, "steps": "x" * 1201}),
    json.dumps({**DRAFT, "when_to_use": 5}),
    json.dumps({k: v for k, v in DRAFT.items() if k != "steps"}),
])
def test_parse_draft_abstains_on_anything_else(text):
    assert skill_reflection.parse_draft(text) is None


def test_tools_may_be_empty():
    assert skill_reflection.parse_draft(json.dumps({**DRAFT, "tools": ""}))["tools"] == ""


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "test")
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "_AGENTS_BY_ID", {"context-summarizer": {"id": "context-summarizer", "url": "http://helper/mcp"}})
    ask = AsyncMock(return_value={"response": json.dumps(DRAFT)})
    monkeypatch.setattr(delegation, "_call_tool", ask)
    sent = []
    monkeypatch.setattr(skill_reflection, "_propose", lambda draft: sent.append(draft) or "Proposed as skill 1.")
    ask.sent = sent
    return ask


CALLS = [("tool_srv_listApps", ["app"]), ("tool_srv_stopApp", ["app"]), ("tool_srv_startApp", ["app"])]


def test_reflect_drafts_with_the_summarizer_and_proposes_the_draft(helper):
    assert asyncio.run(skill_reflection.reflect("restart my app", CALLS, "r")) is True

    url, operation, arguments = helper.call_args.args
    assert (url, operation) == ("http://helper/mcp", "interpret")
    assert arguments["request_id"] == "r" and "restart my app" in arguments["text"]
    assert helper.sent == [{k: v for k, v in DRAFT.items() if k != "save"}]


def test_a_decline_proposes_nothing(helper):
    helper.return_value = {"response": '{"save": false}'}
    assert asyncio.run(skill_reflection.reflect("q", CALLS, "r")) is False
    assert helper.sent == []


def test_no_summarizer_or_no_token_proposes_nothing(helper, monkeypatch):
    monkeypatch.setattr(agent_registry, "_AGENTS_BY_ID", {})
    assert asyncio.run(skill_reflection.reflect("q", CALLS, "r")) is False
    monkeypatch.setattr(internal_auth, "TOKEN", "")
    assert asyncio.run(skill_reflection.reflect("q", CALLS, "r")) is False
    assert helper.sent == []


@pytest.mark.parametrize("failure", [RuntimeError("summarizer down"), PermissionError("tool is switched off"), TimeoutError()])
def test_any_failure_is_silent(helper, monkeypatch, failure):
    helper.side_effect = failure
    assert asyncio.run(skill_reflection.reflect("q", CALLS, "r")) is False

    helper.side_effect = None
    monkeypatch.setattr(skill_reflection, "_propose", lambda draft: (_ for _ in ()).throw(failure))
    assert asyncio.run(skill_reflection.reflect("q", CALLS, "r")) is False


def test_a_slow_summarizer_times_out_quietly(helper, monkeypatch):
    monkeypatch.setattr(skill_reflection, "TIMEOUT_SECONDS", 0.05)

    async def slow(*args):
        await asyncio.sleep(0.5)
        return {"response": json.dumps(DRAFT)}

    helper.side_effect = slow
    assert asyncio.run(skill_reflection.reflect("q", CALLS, "r")) is False
    assert helper.sent == []


def test_the_default_propose_calls_the_skill_tool_through_the_upstream_client(monkeypatch):
    from src.mcp_client import mcp_upstream

    calls = []
    monkeypatch.setattr(mcp_upstream, "call_tool", lambda name, arguments: calls.append((name, arguments)) or "ok")
    draft = {k: v for k, v in DRAFT.items() if k != "save"}

    skill_reflection._propose(draft)

    assert calls == [("main__tool_skill_propose", draft)]


def test_the_proposal_sees_the_turns_identity_in_its_worker_thread(helper, monkeypatch):
    seen = {}
    monkeypatch.setattr(skill_reflection, "_propose", lambda draft: seen.update(uid=internal_auth.current_requester().uid))

    async def scenario():
        token = internal_auth.bind_requester(internal_auth.Requester("alice", "a@x.com", "uid-alice"))
        try:
            task = skill_reflection.schedule("restart", result(*THREE), "r")
        finally:
            internal_auth.reset_requester(token)  # the turn ends before the background task runs
        assert task is not None
        return await task

    assert asyncio.run(scenario()) is True
    assert seen == {"uid": "uid-alice"}


def test_schedule_does_nothing_for_a_turn_that_does_not_qualify(helper):
    async def scenario():
        return skill_reflection.schedule("hi", result(THREE[0]), "r")

    assert asyncio.run(scenario()) is None
    helper.assert_not_called()
