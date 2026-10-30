"""Both provider loops support plan repair, execution and final synthesis."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents import agent_spec, agent_registry, agent_config
from src.agents.roles.orchestrator import delegation, skill_recall, memory_recall, submit_plan
from src.providers import llm_options
from src.providers.base_provider import ChatResult
from src.providers.language import anthropic_provider, openai_provider
from src.runtime import questions
from tests.test_anthropic_provider_streaming import _round_cm
from tests.test_openai_provider import _fake_stream
from tests.test_submit_plan import step


@pytest.fixture
def plan_spec(monkeypatch):
    spec = replace(agent_spec.current(), mode="plan", memory_recall=False, skill_recall=False, skill_learning=False)
    monkeypatch.setattr(agent_spec, "_current", spec)
    return spec


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
def test_only_plan_and_questions_are_offered(monkeypatch, plan_spec, provider):
    monkeypatch.setattr(provider, "list_tools", lambda *_: pytest.fail("plan mode listed capability tools"))
    token = questions.bind(questions.QuestionPolicy(True))
    try:
        names = {s["name"] for s in provider._tool_schemas(roster=[MagicMock()])}
        assert names == {"ask_user", "submit_plan"}
    finally:
        questions.reset(token)


def setup_provider(monkeypatch, provider, batches):
    llm_options.reset_cache()
    monkeypatch.setattr(provider.token_limits, "_config", None)
    monkeypatch.setattr(provider.agent_routing, "roster_for", AsyncMock(return_value=[]))
    monkeypatch.setattr(provider, "list_tools", lambda *_: [])
    monkeypatch.setattr(provider, "_dispatch", lambda *args: pytest.fail("plan mode reached capability dispatch"))
    monkeypatch.setattr(provider.approvals, "review", AsyncMock(side_effect=AssertionError("local tool asked approval")))
    client = MagicMock()
    rounds = []
    for index, batch in enumerate(batches):
        if provider is anthropic_provider:
            blocks = [SimpleNamespace(type="tool_use", id=f"c{index}-{n}", name=name, input=args)
                      for n, (name, args) in enumerate(batch)] if isinstance(batch, list) else []
            final = SimpleNamespace(stop_reason="tool_use" if blocks else "end_turn", content=blocks,
                                    usage=SimpleNamespace(input_tokens=10, output_tokens=5))
            rounds.append(_round_cm([] if blocks else [batch], final))
        else:
            blocks = [SimpleNamespace(type="function_call", call_id=f"c{index}-{n}", name=name,
                                     arguments=json.dumps(args), model_dump=lambda **_: {})
                      for n, (name, args) in enumerate(batch)] if isinstance(batch, list) else []
            final = SimpleNamespace(output=blocks, output_text="" if blocks else batch,
                                    usage=SimpleNamespace(total_tokens=15, input_tokens=10, output_tokens=5))
            rounds.append(_fake_stream([] if blocks else [batch], final))
    stream = client.messages.stream if provider is anthropic_provider else client.responses.stream
    stream.side_effect = rounds
    monkeypatch.setattr(provider, "_get_client", lambda: client)
    agent_registry.register("code-architect", "Code Architect", "http://localhost:9130/mcp", role="architect",
                            focus="Build complete code", kind="code", workers=["worker"])
    return stream


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
def test_one_repair_then_execute_and_synthesize(monkeypatch, plan_spec, provider):
    bad = {"steps": [step(depends_on=["missing"])]}
    good = {"steps": [step()]}
    stream = setup_provider(monkeypatch, provider, [[("submit_plan", bad)], [("submit_plan", good)], "Final reply"])
    calls = []
    def worker(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        calls.append((agent_id, question, depth))
        delegation.record_usage([{"agent_id": agent_id, "total_tokens": 7}])
        return "Finished code"
    monkeypatch.setattr(delegation, "call", worker)
    events = []
    async def emit(event):
        events.append(event)
    async def exercise():
        usage, token = delegation.bind_usage()
        try:
            result = await provider.run_chat("build", [], on_event=emit)
            assert result.response == "Final reply" and result.total_tokens == 45
            assert usage == [{"agent_id": "code-architect", "total_tokens": 7}]
            assert result.tool_calls[0].result == submit_plan.validate(bad, {"code-architect"})[1]
            assert "Finished code" in result.tool_calls[1].result
            assert calls == [("code-architect", step()["brief"], 0)]
            assert "code-architect" in str(stream.call_args_list[0])
            assert "Finished code" in str(stream.call_args_list[-1])
            assert not stream.call_args_list[-1].kwargs.get("tools")
            snapshots = [e["items"] for e in events if e["type"] == "plan_update"]
            assert snapshots[0][0]["status"] == "pending" and snapshots[-1][0]["status"] == "done"
        finally:
            delegation.reset_usage(token)
    asyncio.run(exercise())


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
def test_second_invalid_plan_falls_back_directly_and_never_runs(monkeypatch, plan_spec, provider):
    bad = {"steps": [step(architect="missing")]}
    stream = setup_provider(monkeypatch, provider, [[("submit_plan", bad)], [("submit_plan", bad)], "Direct reply"])
    monkeypatch.setattr(delegation, "call", lambda *_: pytest.fail("invalid plan executed"))
    result = asyncio.run(provider.run_chat("build", []))
    assert result.response == "Direct reply" and len(result.tool_calls) == 2
    assert "Answer directly" in result.tool_calls[-1].result
    assert not stream.call_args_list[-1].kwargs.get("tools")


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
def test_hallucinated_capabilities_and_second_plan_never_execute(monkeypatch, plan_spec, provider):
    good = {"steps": [step()]}
    setup_provider(monkeypatch, provider, [[("main__tool_mem_delete", {}), ("submit_plan", good),
                                          ("submit_plan", good)], "Final"])
    calls = []
    monkeypatch.setattr(delegation, "call", lambda *args: calls.append(args) or "result")
    result = asyncio.run(provider.run_chat("build", []))
    assert result.response == "Final" and len(calls) == 1
    assert "not offered" in result.tool_calls[0].result
    assert "not offered" in result.tool_calls[2].result


def test_skill_recall_plan_text_and_legacy_bytes(monkeypatch, plan_spec):
    monkeypatch.setattr(skill_recall, "_search", lambda _: "1 approved skill(s):\nSkill text")
    output = asyncio.run(skill_recall.with_skills("q", "q"))
    assert "tool_skill_mark" not in output and "Skill text" in output
    monkeypatch.setattr(agent_spec, "_current", replace(plan_spec, mode="legacy"))
    output = asyncio.run(skill_recall.with_skills("q", "q"))
    assert output == skill_recall.LABEL + "\n1 approved skill(s):\nSkill text\n\n[User message]\nq"
    assert "After following one, call tool_skill_mark with its id." in output


def test_plan_mode_keeps_runtime_recall_and_bypasses_entry_routing(monkeypatch, plan_spec):
    monkeypatch.setattr(agent_spec, "_current", replace(plan_spec, memory_recall=True, skill_recall=True))
    monkeypatch.setattr(agent_config.router_routing, "route_turn", AsyncMock(side_effect=AssertionError("plan routed")))
    memory = AsyncMock(return_value="memory question")
    skills = AsyncMock(return_value="skills and memory question")
    monkeypatch.setattr(memory_recall, "with_recall", memory)
    monkeypatch.setattr(skill_recall, "with_skills", skills)
    provider = SimpleNamespace(run_chat=AsyncMock(return_value=ChatResult(response="ok")), DEFAULT_MODEL="model")
    monkeypatch.setattr(agent_config, "_PROVIDER_MODULE", provider)
    result = asyncio.run(agent_config.run_chat("q", [], []))
    assert result.response == "ok"
    memory.assert_awaited_once()
    skills.assert_awaited_once()
    assert provider.run_chat.call_args.args[0] == "skills and memory question"


def test_architect_does_not_enter_generic_provider_loop(monkeypatch, plan_spec):
    monkeypatch.setattr(agent_spec, "_current", replace(plan_spec, role="architect", entry=False, kind="code"))
    with pytest.raises(NotImplementedError, match="phase"):
        asyncio.run(agent_config.run_chat("brief", [], []))


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
def test_direct_answer_runs_no_architect(monkeypatch, plan_spec, provider):
    setup_provider(monkeypatch, provider, ["Direct answer"])
    monkeypatch.setattr(delegation, "call", lambda *_: pytest.fail("direct answer delegated"))
    result = asyncio.run(provider.run_chat("hello", []))
    assert result.response == "Direct answer" and not result.tool_calls


@pytest.mark.parametrize("provider", [anthropic_provider, openai_provider])
def test_failed_architect_skips_dependents_and_is_in_final_prompt(monkeypatch, plan_spec, provider):
    submitted = {"steps": [step(), step("s2", depends_on=["s1"])]}
    setup_provider(monkeypatch, provider, [[("submit_plan", submitted)], "Could not complete"])
    calls = []
    def fail(*args):
        calls.append(args)
        raise RuntimeError("architect unavailable")
    monkeypatch.setattr(delegation, "call", fail)
    result = asyncio.run(provider.run_chat("build", []))
    assert len(calls) == agent_spec.ArchitectLimits().max_retries + 1
    rows = json.loads(result.tool_calls[0].result)["steps"]
    assert rows["s1"]["status"] == "failed" and rows["s1"]["error"] == "architect unavailable"
    assert rows["s2"]["status"] == "skipped"


def test_architect_server_registers_kind_and_workers_from_temp_file(monkeypatch, tmp_path):
    from src import server
    from tests.test_architect_spec import BASE, write
    spec = agent_spec.load_file(write(tmp_path, BASE))
    monkeypatch.setattr(server, "SPEC", spec)
    monkeypatch.setattr(server, "_AGENT_ID", spec.id)
    monkeypatch.setattr(server, "_AGENT_LABEL", spec.label)
    for name in ("connect", "warn_unmatched_tool_globs", "close"):
        monkeypatch.setattr(server.mcp_upstream, name, lambda: None)
    registrations = []
    monkeypatch.setattr(server.agent_registry, "register", lambda *args, **kwargs: registrations.append(kwargs))
    monkeypatch.setattr(server.agent_registry, "deregister", lambda *_: None)
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: None)
    server.main()
    assert registrations[0]["kind"] == "code" and registrations[0]["workers"] == ["worker"]
