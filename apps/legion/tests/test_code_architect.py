"""CodeArchitect phases use canned completions and workers, never a network."""

import asyncio
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_spec, agent_config
from src.agents.roles.architect import pipeline, registry
from src.agents.roles.orchestrator import delegation
from src.providers import cancellation
from src.providers.base_provider import ChatCancelled, ChatResult


def unit(id="a", **extra):
    return {"id": id, "name": id, "spec": f"Implement {id} as specified.", "signature": f"def {id}():",
            "depends_on": [], "effect": "read", "needs_body_of": [], "tier_hint": "light", **extra}


def plan(*units, language="python"):
    return json.dumps({"language": language, "units": list(units or [unit()])})


@pytest.fixture
def spec(monkeypatch):
    monkeypatch.setenv("AI_AGENT_GATEWAY", "omniroute")
    value = replace(agent_spec.current(), id="code-architect", label="Code Architect", role="architect",
                    kind="code", entry=False, workers=("code-writer",), prefetch=(), plan_tool=False,
                    llm=replace(agent_spec.current().llm, gateway="omniroute"),
                    limits=agent_spec.ArchitectLimits(unit_timeout_seconds=1))
    monkeypatch.setattr(agent_spec, "_current", value)
    return value


def completion_sequence(responses, calls):
    responses = iter(responses)
    def complete(prompt):
        calls.append(prompt)
        return ChatResult(response=next(responses), provider_id="anthropic", gateway="omniroute",
                          model="combo/heavy", input_tokens=10, output_tokens=5, total_tokens=15)
    return complete


@pytest.mark.parametrize("fenced", [False, True])
def test_pipeline_dependency_signatures_bodies_waves_and_usage(monkeypatch, spec, tmp_path, fenced):
    nodes = [unit(), unit("b"), unit("c", depends_on=["a", "b"], needs_body_of=["a"])]
    raw = plan(*nodes)
    if fenced:
        raw = "```json\n" + raw + "\n```"
    prompts, calls, completed = [], [], []
    active = maximum = 0
    lock = threading.Lock()
    def worker(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            calls.append((question, depth, model_tier, list(completed)))
        name = next(n["id"] for n in nodes if f"Implement {n['id']} as specified." in question)
        time.sleep(0.02)
        with lock:
            active -= 1
            completed.append(name)
        delegation.record_usage([{"agent_id": agent_id, "model": "worker-model", "total_tokens": 3,
                                 "request_id": f"child-{name}", "depth": 2, "delegated_by": spec.id}])
        return f"```python\ndef {name}():\n    return '{name} body'\n```"
    monkeypatch.setattr(delegation, "call", worker)
    monkeypatch.setenv("AI_AGENT_USAGE_DIR", str(tmp_path))
    result = asyncio.run(pipeline.run(spec, "Build three functions", completion_sequence(
        [raw, "```python\ndef a(): pass\ndef b(): pass\ndef c(): return a()\n```"], prompts),
        request_id="architect-request", depth=1, delegated_by="ember"))
    assert result.status == "done" and maximum == 2
    assert len(calls) == 3 and set(calls[-1][3]) == {"a", "b"}
    question = calls[-1][0]
    assert "def a():" in question and "def b():" in question
    assert "a body" in question and "b body" not in question
    assert "data" in question and all(c[1:3] == (1, "light") for c in calls)
    rows = result.delegated_usage
    assert len(rows) == 5 and len(prompts) == 2
    own = [row for row in rows if row["agent_id"] == spec.id]
    assert all(row["provider_id"] == "anthropic" and row["gateway"] == "omniroute" and
               row["model"] == "combo/heavy" and row["request_id"] == "architect-request" and
               row["depth"] == 1 and row["delegated_by"] == "ember" and row["total_tokens"] == 15 and
               row["started_at"] <= row["finished_at"] for row in own)
    assert len(list(tmp_path.glob("*.jsonl"))) == 1
    assert len(next(tmp_path.glob("*.jsonl")).read_text().splitlines()) == 2


@pytest.mark.parametrize("raw,error", [
    ("not json", "JSON"), ("[]", "object"),
    (plan(unit(), unit()), "duplicate"),
    (plan(unit(depends_on=["a"])), "cycle"),
    (plan(unit(depends_on=["missing"])), "unknown"),
    (plan(unit(needs_body_of=["missing"])), "needs_body_of"),
    (plan(unit(effect="write")), "effect"), (plan(unit(tier_hint="extreme")), "tier_hint"),
    (plan(unit(agent_id="model-chosen")), "agent_id"), (plan(unit(spec="")), "spec"),
    (json.dumps({"language": "python", "units": []}), "units"),
    (json.dumps({"language": 1, "units": [unit()]}), "language"),
])
def test_plan_strict_validation(spec, raw, error):
    with pytest.raises(ValueError, match=error):
        registry.KINDS["code"].parse_plan(raw, spec)


def test_max_units_and_worker_assignment(spec):
    handler = registry.KINDS["code"]
    with pytest.raises(ValueError, match="units"):
        handler.parse_plan(plan(unit(), unit("b")), replace(spec, limits=replace(spec.limits, max_units=1)))
    parsed = handler.parse_plan(plan(unit()), spec)
    assert parsed.units[0].agent_id == "code-writer"


@pytest.mark.parametrize("repair_succeeds", [False, True])
def test_one_plan_repair_with_exact_error(monkeypatch, spec, repair_succeeds):
    prompts = []
    raw = "broken json"
    try:
        registry.KINDS["code"].parse_plan(raw, spec)
    except ValueError as error:
        exact_error = str(error)
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(): pass")
    responses = [raw, plan(unit()) if repair_succeeds else raw, "def a(): pass"]
    if repair_succeeds:
        result = asyncio.run(pipeline.run(spec, "Build a function", completion_sequence(responses, prompts)))
        assert result.status == "done" and len(result.delegated_usage) == 3
    else:
        with pytest.raises(RuntimeError, match="JSON") as raised:
            asyncio.run(pipeline.run(spec, "Build a function", completion_sequence(responses, prompts)))
        assert str(raised.value) == exact_error and len(prompts) == 2
    assert exact_error in prompts[1] and raw in prompts[1]


@pytest.mark.parametrize("succeed", [False, True])
def test_python_unit_parse_failure_retries_and_assemble_gets_missing(monkeypatch, spec, succeed):
    prompts, tiers = [], []
    def worker(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        tiers.append(model_tier)
        return "```python\ndef a(): pass\n```" if succeed and len(tiers) >= 2 else "```python\ndef a(:\n```"
    monkeypatch.setattr(delegation, "call", worker)
    result = asyncio.run(pipeline.run(spec, "Build functions", completion_sequence(
        [plan(unit(), unit("b", depends_on=["a"])), "```python\ndef a(): pass\n```"], prompts)))
    assert tiers[:2] == ["light", "standard"]
    if succeed:
        assert result.status == "done" and len(tiers) == 3
    else:
        assert result.status == "failed" and len(tiers) == 2
        assert "failed" in prompts[-1] and "skipped" in prompts[-1]
        assert "Incomplete" in result.response and "a" in result.response and "b" in result.response


@pytest.mark.parametrize("brief,prefetch", [("Build a function", False), ("Fix src/example.py", True),
                                           ("Fix RTOSLite.cpp", True)])
def test_prefetch_is_conservative_and_nonfatal(monkeypatch, spec, caplog, brief, prefetch):
    spec = replace(spec, prefetch=("repo-helper",))
    prompts, calls = [], []
    def worker(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        calls.append(agent_id)
        if agent_id == "repo-helper":
            raise RuntimeError("repo helper unavailable")
        return "def a(): pass"
    monkeypatch.setattr(delegation, "call", worker)
    result = asyncio.run(pipeline.run(spec, brief, completion_sequence([plan(unit()), "def a(): pass"], prompts)))
    assert result.status == "done"
    assert ("repo-helper" in calls) is prefetch
    assert ("prefetch" in caplog.text.lower()) is prefetch


def test_prefetch_output_is_capped(monkeypatch, spec):
    prompts = []
    monkeypatch.setattr(delegation, "call", lambda agent_id, *args: "x" * 9000 if agent_id == "repo-helper" else "def a(): pass")
    asyncio.run(pipeline.run(replace(spec, prefetch=("repo-helper",)), "Fix src/a.py", completion_sequence(
        [plan(unit()), "def a(): pass"], prompts)))
    assert "x" * 8000 in prompts[0] and "x" * 8001 not in prompts[0]


def test_nonpython_skips_ast_and_assemble_warns_on_invalid_python(monkeypatch, spec):
    prompts = []
    monkeypatch.setattr(delegation, "call", lambda *args: "```cpp\nint a() { return 0; }\n```")
    result = asyncio.run(pipeline.run(spec, "Build C++", completion_sequence(
        [plan(unit(signature="int a()"), language="cpp"), "```cpp\nint a() {}\n```"], prompts)))
    assert result.status == "done"
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(): pass")
    result = asyncio.run(pipeline.run(spec, "Build Python", completion_sequence(
        [plan(unit()), "```python\ndef a(:\n```"], [])))
    assert "syntax" in result.response.lower() and result.status == "failed"


def test_assembly_prompt_checks_signatures_and_pasted_names(monkeypatch, spec):
    prompts = []
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(): pass")
    asyncio.run(pipeline.run(spec, "Use the user's existing API:\n```cpp\nvoid begin();\n```",
        completion_sequence([plan(unit()), "def a(): pass"], prompts)))
    assert "begin" in prompts[-1] and "def a():" in prompts[-1]
    assert "every call" in prompts[-1].lower() and "possible invented API" in prompts[-1]


def test_final_python_review_flags_unplanned_calls_and_accepts_pasted_definitions(monkeypatch, spec):
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(): pass")
    result = asyncio.run(pipeline.run(spec, "Build from this code:\n```python\ndef begin(): pass\n```",
        completion_sequence([plan(unit()), "```python\ndef a():\n    begin()\n    run()\n```"], [])))
    assert "possible invented API" in result.response and "run" in result.response
    assert "begin" not in result.response.split("possible invented API")[-1]


def test_server_worker_usage_includes_request_id_and_depth(monkeypatch):
    from src import server
    monkeypatch.setattr(server.agent_config, "run_chat", AsyncMock(return_value=ChatResult(response="body")))
    reply = asyncio.run(server.ask("Build a function", request_id="worker-child", depth=2,
                                   delegated_by="code-architect"))
    row = reply["agent_usage"][0]
    assert row["request_id"] == "worker-child" and row["depth"] == 2
    assert row["delegated_by"] == "code-architect"


def test_cancellation_mid_executor_never_assembles(monkeypatch, spec):
    prompts = []
    def worker(*args):
        cancellation.cancel("code-cancel")
        return "def a(): pass"
    monkeypatch.setattr(delegation, "call", worker)
    try:
        with pytest.raises(ChatCancelled):
            asyncio.run(pipeline.run(spec, "Build a function", completion_sequence([plan(unit())], prompts),
                                    request_id="code-cancel", depth=1))
        assert len(prompts) == 1
    finally:
        cancellation.clear("code-cancel")


def test_agent_config_uses_provider_one_shot_and_returns_per_call_usage(monkeypatch, spec):
    from src import server
    prompts, models = [], []
    replies = completion_sequence([plan(unit()), "def a(): pass"], prompts)
    def complete(text, model=None):
        models.append(model)
        return replies(text)
    monkeypatch.setattr(agent_config._PROVIDER_MODULE, "run_interpret", complete)
    monkeypatch.setattr(agent_config._PROVIDER_MODULE, "run_chat", AsyncMock(side_effect=AssertionError("tool loop")))
    monkeypatch.setattr(delegation, "call", lambda *args: "def a(): pass")
    monkeypatch.setattr(server, "SPEC", spec)
    monkeypatch.setattr(server, "_AGENT_ID", spec.id)
    monkeypatch.setattr(server, "_AGENT_LABEL", spec.label)
    reply = asyncio.run(server.ask("Build a function", request_id="ask-request", depth=1, delegated_by="ember"))
    assert reply["status"] == "done" and len(reply["units"]) == 1
    assert len(reply["agent_usage"]) == 2
    assert all(row["request_id"] == "ask-request" and row["depth"] == 1 and row["delegated_by"] == "ember"
               for row in reply["agent_usage"])
    assert reply["total_tokens"] == 30 and models == ["combo/heavy"] * 2


def test_cancellation_interrupts_one_shot_wait_and_late_usage_is_logged(monkeypatch, spec, tmp_path):
    started, release = threading.Event(), threading.Event()
    def complete(prompt):
        started.set()
        release.wait(2)
        return ChatResult(response=plan(unit()), total_tokens=7)
    monkeypatch.setenv("AI_AGENT_USAGE_DIR", str(tmp_path))
    async def exercise():
        task = asyncio.create_task(pipeline.run(spec, "Build a function", complete, request_id="slow-completion"))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.005)
            assert started.is_set()
            cancellation.cancel("slow-completion")
            with pytest.raises(ChatCancelled):
                await asyncio.wait_for(task, 1)
        finally:
            release.set()
        for _ in range(200):
            paths = list(tmp_path.glob("*.jsonl"))
            if paths and paths[0].read_text():
                break
            await asyncio.sleep(0.005)
        assert json.loads(paths[0].read_text())["total_tokens"] == 7
    try:
        asyncio.run(exercise())
    finally:
        cancellation.clear("slow-completion")


@pytest.mark.parametrize("provider_name", ["anthropic_provider", "openai_provider"])
def test_real_one_shot_interfaces_offer_no_tools_and_report_usage(monkeypatch, provider_name):
    from src.providers.language import anthropic_provider, openai_provider
    provider = {"anthropic_provider": anthropic_provider, "openai_provider": openai_provider}[provider_name]
    client = MagicMock()
    monkeypatch.setattr(provider, "_get_sync_client", lambda *args: client)
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15)
    if provider is anthropic_provider:
        client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="answer")], usage=usage)
        create = client.messages.create
    else:
        client.responses.create.return_value = SimpleNamespace(output_text="answer", usage=usage)
        create = client.responses.create
    result = provider.run_interpret("brief", "explicit-heavy-model")
    assert "tools" not in create.call_args.kwargs
    assert create.call_args.kwargs["model"] == "explicit-heavy-model"
    assert result.model == "explicit-heavy-model" and result.gateway
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (10, 5, 15)
