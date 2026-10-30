"""Architect failures preserve billing rows and block dependent outer steps."""

import asyncio
from functools import partial

from src.agents import agent_registry
from src.agents.roles.architect.executor import DagExecutor, call_worker
from src.agents.roles.architect.types import Step
from src.agents.roles.orchestrator import delegation
from tests.test_code_architect import completion_sequence, plan, spec, unit


def test_failed_architect_reply_retries_then_skips_and_preserves_usage(monkeypatch):
    agent_registry.register("code-architect", "Code Architect", "http://architect/mcp", role="architect", kind="code")
    tiers, events = [], []
    async def remote(url, name, arguments, on_progress=None):
        assert name == "ask"
        tiers.append(arguments["model_tier"])
        return {"status": "failed", "response": "Incomplete unit a", "agent_usage": [
            {"agent_id": "code-architect", "total_tokens": 15, "request_id": arguments["request_id"]}]}
    monkeypatch.setattr(delegation, "_call_tool", remote)
    async def exercise():
        rows, token = delegation.bind_usage()
        async def emit(event):
            events.append(event)
        try:
            results = await DagExecutor(emit_agent_events=False).run([
                Step("s1", "code-architect", "Build a", effect="read"),
                Step("s2", "code-architect", "Build b", depends_on=("s1",), effect="read")],
                partial(call_worker, on_event=emit))
            assert tiers == ["standard", "heavy"]
            assert results["s1"].status == "failed" and results["s1"].error == "Incomplete unit a"
            assert results["s2"].status == "skipped"
            assert len(rows) == 2 and all(row["total_tokens"] == 15 for row in rows)
            assert len({row["request_id"] for row in rows}) == 2
            assert [e["ok"] for e in events if e["type"] == "agent_end"] == [False, False]
        finally:
            delegation.reset_usage(token)
    asyncio.run(exercise())


def test_two_invalid_plans_return_both_usage_rows_to_caller(monkeypatch, spec):
    from src import server
    from src.agents import agent_config
    prompts = []
    complete = completion_sequence(["broken", "broken"], prompts)
    monkeypatch.setattr(agent_config._PROVIDER_MODULE, "run_interpret", lambda text, model=None: complete(text))
    monkeypatch.setattr(server, "SPEC", spec)
    monkeypatch.setattr(server, "_AGENT_ID", spec.id)
    monkeypatch.setattr(server, "_AGENT_LABEL", spec.label)
    reply = asyncio.run(server.ask("Build a function", request_id="bad-plan", depth=1, delegated_by="ember"))
    assert reply["status"] == "failed" and "Invalid plan JSON" in reply["response"]
    assert len(reply["agent_usage"]) == 2
    assert sum(row["total_tokens"] for row in reply["agent_usage"]) == 30
    assert all(row["request_id"] == "bad-plan" and row["delegated_by"] == "ember" for row in reply["agent_usage"])


def test_python_call_checks_keep_qualification_and_required_arguments(monkeypatch, spec):
    from src.agents.roles.architect import pipeline
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(value): pass")
    result = asyncio.run(pipeline.run(spec, "Pasted code:\n```python\ndef begin(): pass\n```",
        completion_sequence([plan(unit(signature="def a(value):")),
            "```python\ndef a(value):\n    device.begin()\n\na()\n```"], [])))
    assert "possible invented API" in result.response
    warning = result.response.split("possible invented API")[-1]
    assert "device.begin" in warning and "a()" in warning


def test_python_pasted_method_with_known_class_receiver_is_accepted(monkeypatch, spec):
    from src.agents.roles.architect import pipeline
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(): pass")
    result = asyncio.run(pipeline.run(spec, "Pasted code:\n```python\nclass Device:\n    def begin(self): pass\n```",
        completion_sequence([plan(unit()), "```python\ndef a():\n    device = Device()\n    device.begin()\n```"], [])))
    assert "possible invented API" not in result.response


def test_cancelled_architect_reply_keeps_completed_planner_usage(monkeypatch, spec):
    from src import server
    from src.agents import agent_config
    from src.providers import cancellation
    complete = completion_sequence([plan(unit())], [])
    monkeypatch.setattr(agent_config._PROVIDER_MODULE, "run_interpret", lambda text, model=None: complete(text))
    def worker(*args):
        cancellation.cancel("cancelled-architect")
        return "def a(): pass"
    monkeypatch.setattr(delegation, "call", worker)
    monkeypatch.setattr(server, "SPEC", spec)
    reply = asyncio.run(server.ask("Build a function", request_id="cancelled-architect", depth=1,
                                   delegated_by="ember"))
    assert reply["cancelled"] is True
    assert len(reply["agent_usage"]) == 1 and reply["agent_usage"][0]["total_tokens"] == 15
