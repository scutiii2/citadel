"""supervisor.py tests with real (tiny) child processes: output is
prefixed, a crash deregisters and restarts with backoff, the fifth crash
in the window gives up, stop() ends children promptly, and leftover
registry entries for our own agents are cleared at start."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import sys

from src import supervisor
from src.agents.agent_spec import AgentSpec, LlmSpec


def _spec(agent_id, port=9200, enabled=True, tmp_path=None):
    return AgentSpec(id=agent_id, label=agent_id, port=port, llm=LlmSpec(provider="anthropic"),
                     enabled=enabled, source=(tmp_path / f"{agent_id}.json") if tmp_path else None)


def test_crash_policy_backoff_and_give_up():
    now = [0.0]
    policy = supervisor.CrashPolicy(max_crashes=5, window=300.0, base=1.0, cap=4.0, clock=lambda: now[0])
    delays = [policy.record() for _ in range(4)]
    assert delays == [1.0, 2.0, 4.0, 4.0]
    assert policy.record() is None


def test_crash_policy_forgets_old_crashes():
    now = [0.0]
    policy = supervisor.CrashPolicy(max_crashes=2, window=10.0, clock=lambda: now[0])
    assert policy.record() == 1.0
    now[0] = 20.0
    assert policy.record() == 1.0


def test_child_env_points_at_the_agent_file(tmp_path):
    env = supervisor.child_env(_spec("calc", port=9103, tmp_path=tmp_path))
    assert env["AI_AGENT_FILE"] == str(tmp_path / "calc.json")
    assert env["AI_AGENT_PORT"] == "9103"
    assert env["PYTHONUNBUFFERED"] == "1"


def test_crashing_child_is_prefixed_deregistered_restarted_then_failed(tmp_path):
    lines, deregistered, sleeps = [], [], []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    sup = supervisor.Supervisor(
        [_spec("calc", tmp_path=tmp_path), _spec("off", enabled=False, tmp_path=tmp_path)],
        command_for=lambda spec: [sys.executable, "-c", "print('hello from child'); raise SystemExit(3)"],
        deregister=deregistered.append,
        out=lines.append,
        policy_factory=lambda: supervisor.CrashPolicy(max_crashes=2),
        sleep=fake_sleep,
    )

    asyncio.run(asyncio.wait_for(sup.run(), timeout=30))

    assert lines.count("[calc] hello from child") == 2
    assert any("restarting in 1s" in line for line in lines)
    assert any("not restarting" in line for line in lines)
    assert sleeps == [1.0]
    # start-up cleanup for both files, one crash before the restart, one
    # after the final crash, then the shutdown sweep.
    assert deregistered[:2] == ["calc", "off"]
    assert deregistered.count("calc") >= 3
    assert "off" not in deregistered[2:]


def test_stop_terminates_a_running_child_quickly(tmp_path):
    lines = []

    async def scenario():
        sup = supervisor.Supervisor(
            [_spec("calc", tmp_path=tmp_path)],
            command_for=lambda spec: [sys.executable, "-c", "import time; print('up', flush=True); time.sleep(60)"],
            deregister=lambda agent_id: None,
            out=lines.append,
        )
        task = asyncio.create_task(sup.run())
        for _ in range(200):
            if "[calc] up" in lines:
                break
            await asyncio.sleep(0.05)
        await sup.stop()
        await asyncio.wait_for(task, timeout=15)

    asyncio.run(scenario())
    assert "[calc] up" in lines


def test_overlong_output_line_is_truncated_and_supervisor_survives(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "LINE_LIMIT", 4096)
    lines = []
    code = "import sys; sys.stdout.write('x' * 200000 + '\\n'); print('after', flush=True)"
    sup = supervisor.Supervisor(
        [_spec("calc", tmp_path=tmp_path)],
        command_for=lambda spec: [sys.executable, "-c", code],
        deregister=lambda agent_id: None,
        out=lines.append,
        policy_factory=lambda: supervisor.CrashPolicy(max_crashes=1),
    )
    asyncio.run(asyncio.wait_for(sup.run(), timeout=30))
    assert "[calc] <line too long, truncated>" in lines
    assert "[calc] after" in lines
    assert not any(len(line) > 5000 for line in lines)


def test_spawn_failure_only_fails_that_child(tmp_path):
    lines, sleeps = [], []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    def command_for(spec):
        if spec.id == "broken":
            return [str(tmp_path / "no-such-executable")]
        return [sys.executable, "-c", "import time; print('up', flush=True); time.sleep(60)"]

    async def scenario():
        sup = supervisor.Supervisor(
            [_spec("broken", tmp_path=tmp_path), _spec("ok", tmp_path=tmp_path)],
            command_for=command_for,
            deregister=lambda agent_id: None,
            out=lines.append,
            policy_factory=lambda: supervisor.CrashPolicy(max_crashes=2),
            sleep=fake_sleep,
        )
        task = asyncio.create_task(sup.run())
        for _ in range(200):
            if "[ok] up" in lines and sup._children[0].failed:
                break
            await asyncio.sleep(0.05)
        assert not task.done()
        assert sup._children[0].failed
        assert not sup._children[1].failed
        await sup.stop()
        await asyncio.wait_for(task, timeout=15)

    asyncio.run(scenario())
    assert any(line.startswith("[supervisor] broken failed:") for line in lines)
    assert any("not restarting" in line for line in lines)
    assert sleeps == [1.0]


def test_stop_during_spawn_does_not_orphan_the_child(tmp_path):
    holder = []

    def command_for(spec):
        # stop() runs while create_subprocess_exec is still awaiting.
        asyncio.get_running_loop().create_task(holder[0].stop())
        return [sys.executable, "-c", "import time; time.sleep(60)"]

    async def scenario():
        child = supervisor.AgentProcess(
            _spec("calc", tmp_path=tmp_path), command_for, lambda agent_id: None,
            lambda line: None, supervisor.CrashPolicy(), asyncio.sleep,
        )
        holder.append(child)
        try:
            await asyncio.wait_for(child.run(), timeout=5)
        finally:
            if child._proc is not None and child._proc.returncode is None:
                child._proc.kill()
        return child

    child = asyncio.run(scenario())
    assert child._proc.returncode is not None


def test_start_publishes_every_defined_agent_including_disabled(tmp_path):
    published = []
    specs = [_spec("calc", tmp_path=tmp_path), _spec("off", enabled=False, tmp_path=tmp_path)]
    sup = supervisor.Supervisor(
        specs,
        command_for=lambda spec: [sys.executable, "-c", "pass"],
        deregister=lambda agent_id: None,
        out=lambda line: None,
        policy_factory=lambda: supervisor.CrashPolicy(max_crashes=1),
        sleep=lambda seconds: asyncio.sleep(0),
        publish=published.append,
    )

    asyncio.run(asyncio.wait_for(sup.run(), timeout=30))

    assert published == [specs]


def test_start_prunes_registry_entries_for_agents_no_longer_defined(tmp_path):
    asked, lines = [], []
    sup = supervisor.Supervisor(
        [_spec("calc", tmp_path=tmp_path), _spec("off", enabled=False, tmp_path=tmp_path)],
        command_for=lambda spec: [sys.executable, "-c", "pass"],
        deregister=lambda agent_id: None,
        out=lines.append,
        policy_factory=lambda: supervisor.CrashPolicy(max_crashes=1),
        sleep=lambda seconds: asyncio.sleep(0),
        publish=lambda specs: None,
        prune=lambda ids: asked.append(list(ids)) or ["planner"],
    )

    asyncio.run(asyncio.wait_for(sup.run(), timeout=30))

    assert asked == [["calc", "off"]]
    assert "[supervisor] dropped dead registry entries: planner" in lines


def test_watching_supervisor_starts_restarts_and_stops_children(tmp_path):
    import json

    lines = []

    def write(agent_id, port, **extra):
        data = {"role": "specialist", "port": port, "llm": {"provider": "anthropic"}, **extra}
        (tmp_path / f"{agent_id}.json").write_text(json.dumps(data), encoding="utf-8")

    write("ember", 9301, entry=True)
    from src.agents import agent_spec

    async def scenario():
        sup = supervisor.Supervisor(
            agent_spec.load_dir(tmp_path),
            command_for=lambda spec: [sys.executable, "-c", f"print('up {spec.port}', flush=True); import time; time.sleep(60)"],
            deregister=lambda agent_id: None,
            publish=lambda specs: None,
            out=lines.append,
            watch_dir=tmp_path,
            poll_seconds=0.1,
        )
        task = asyncio.create_task(sup.run())

        async def until(text):
            for _ in range(300):
                if text in lines:
                    return
                await asyncio.sleep(0.05)
            raise AssertionError(f"{text!r} never appeared in {lines}")

        await until("[ember] up 9301")
        write("calc", 9302)
        await until("[calc] up 9302")
        write("calc", 9303)
        await until("[calc] up 9303")
        (tmp_path / "calc.json").unlink()
        await until("[supervisor] stopped calc")
        (tmp_path / "ember.json").write_text("{not json", encoding="utf-8")
        await asyncio.sleep(0.4)
        assert not task.done() and "[supervisor] stopped ember" not in lines
        await sup.stop()
        await asyncio.wait_for(task, timeout=15)

    asyncio.run(scenario())


def test_changing_a_shared_file_restarts_every_agent(tmp_path):
    import json

    from src.agents import agent_spec

    (tmp_path / "ember.json").write_text(json.dumps({"role": "specialist", "port": 9401, "entry": True, "llm": {"provider": "anthropic"}}), encoding="utf-8")
    shared = tmp_path / "shared.txt"
    lines = []

    async def scenario():
        sup = supervisor.Supervisor(
            agent_spec.load_dir(tmp_path),
            command_for=lambda spec: [sys.executable, "-c", "print('up', flush=True); import time; time.sleep(60)"],
            deregister=lambda agent_id: None,
            publish=lambda specs: None,
            out=lines.append,
            watch_dir=tmp_path,
            poll_seconds=0.1,
            restart_on=[shared],
        )
        task = asyncio.create_task(sup.run())

        async def until(count):
            for _ in range(300):
                if lines.count("[ember] up") >= count:
                    return
                await asyncio.sleep(0.05)
            raise AssertionError(lines)

        await until(1)
        shared.write_text("changed", encoding="utf-8")
        await until(2)
        assert "[supervisor] shared files changed - restarted every agent" in lines
        await sup.stop()
        await asyncio.wait_for(task, timeout=15)

    asyncio.run(scenario())


# Startup validates Laya's configured service strategy before spawning agents.


def test_unknown_laya_strategy_stops_the_start(monkeypatch):
    from src.providers.decision import laya_model

    class Service:
        configured = True
        def strategies(self):
            return {"strategies": ["english-only", "english-then-typed"], "default": "auto"}

    monkeypatch.setattr(laya_model, "agent", lambda: Service())
    monkeypatch.setattr(supervisor.llm_config, "load_gateways", lambda: {"decision": {"laya": {"strategy": "nope"}}})
    with pytest.raises(SystemExit, match="nope.*not offered.*english-only"):
        supervisor.check_laya_strategy(uses_laya=True)


def test_unreachable_service_only_warns(monkeypatch, caplog):
    from src.providers.decision import laya_model

    class Down:
        configured = True
        def strategies(self):
            raise laya_model.LayaServiceError("down")

    monkeypatch.setattr(laya_model, "agent", lambda: Down())
    supervisor.check_laya_strategy(uses_laya=True)
    assert "down" in caplog.text


def test_offered_laya_strategy_allows_start(monkeypatch):
    from src.providers.decision import laya_model

    service = SimpleNamespace(configured=True, strategies=lambda: {"strategies": ["english-then-typed"]})
    monkeypatch.setattr(laya_model, "agent", lambda: service)
    monkeypatch.setattr(supervisor.llm_config, "load_gateways", lambda: {})
    supervisor.check_laya_strategy(uses_laya=True)


def test_no_laya_user_does_not_contact_service(monkeypatch):
    from src.providers.decision import laya_model

    def unexpected():
        raise AssertionError("Laya should not be contacted")
    monkeypatch.setattr(laya_model, "agent", unexpected)
    supervisor.check_laya_strategy(uses_laya=False)


@pytest.mark.parametrize(("provider", "strategy", "enabled", "expected"), [
    ("decision", "both", True, True), ("decision", "laya-only", True, True),
    ("decision", "jev-only", True, False), ("decision", "both", False, False),
    ("anthropic", None, True, False),
])
def test_start_checks_only_enabled_agents_that_use_laya(monkeypatch, provider, strategy, enabled, expected):
    spec = SimpleNamespace(role="specialist", enabled=enabled, llm=SimpleNamespace(provider=provider, strategy=strategy))
    seen = []
    class Runner:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self):
            seen.append("start")
    monkeypatch.setattr(supervisor.agent_spec, "load_dir", lambda *args: [spec])
    monkeypatch.setattr(supervisor, "check_laya_strategy", lambda uses_laya: seen.append(uses_laya))
    monkeypatch.setattr(supervisor, "Supervisor", Runner)
    monkeypatch.setattr(supervisor, "dotenv_values", lambda path: {}, raising=False)
    supervisor.main()
    assert seen == [expected, "start"]


@pytest.mark.parametrize(("llm_strategy", "policy_strategy", "expected"), [
    ("jev-only", "laya-only", True), ("laya-only", "jev-only", False),
])
def test_start_uses_router_policy_strategy(monkeypatch, llm_strategy, policy_strategy, expected):
    spec = SimpleNamespace(role="router", enabled=True,
                           llm=SimpleNamespace(provider="decision", strategy=llm_strategy),
                           decision=SimpleNamespace(strategy=policy_strategy))
    seen = []
    class Runner:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self):
            pass
    monkeypatch.setattr(supervisor.agent_spec, "load_dir", lambda *args: [spec])
    monkeypatch.setattr(supervisor, "check_laya_strategy", lambda uses_laya: seen.append(uses_laya))
    monkeypatch.setattr(supervisor, "dotenv_values", lambda path: {}, raising=False)
    monkeypatch.setattr(supervisor, "Supervisor", Runner)
    supervisor.main()
    assert seen == [expected]


def test_start_loads_laya_environment_before_validation(monkeypatch):
    monkeypatch.delenv("LAYA_SERVICE_URL", raising=False)
    monkeypatch.setenv("LAYA_TOKEN", "process-token")
    monkeypatch.delenv("UNRELATED_STARTUP_TEST_KEY", raising=False)
    monkeypatch.setattr(supervisor, "dotenv_values", lambda path: {
        "LAYA_SERVICE_URL": "http://laya.test", "LAYA_TOKEN": "file-token",
        "UNRELATED_STARTUP_TEST_KEY": "ignore",
    }, raising=False)
    monkeypatch.setattr(supervisor.agent_spec, "load_dir", lambda *args: [
        SimpleNamespace(role="specialist", enabled=True, llm=SimpleNamespace(provider="decision", strategy="both"))])
    monkeypatch.setattr(supervisor.llm_config, "load_gateways", lambda: {"decision": {"laya": {"strategy": "bad"}}})
    seen = []
    def strategies(service):
        seen.append((service._url, service._token))
        return {"strategies": ["english-only"]}
    monkeypatch.setattr(supervisor.laya_model, "_agent", None)
    monkeypatch.setattr(supervisor.laya_model.LAYAModel, "strategies", strategies)
    def unexpected_start(*args, **kwargs):
        raise AssertionError("invalid Laya strategy must stop startup before children are created")
    monkeypatch.setattr(supervisor, "Supervisor", unexpected_start)
    with pytest.raises(SystemExit, match="bad.*not offered"):
        supervisor.main()
    assert seen == [("http://laya.test", "process-token")]
    assert "UNRELATED_STARTUP_TEST_KEY" not in supervisor.os.environ


@pytest.mark.parametrize(("auto_route", "expected"), [
    (SimpleNamespace(enabled=True, strategy="both"), True),
    (SimpleNamespace(enabled=True, strategy="jev-only"), False),
    (SimpleNamespace(enabled=False, strategy="both"), False),
])
def test_features_using_laya_count_for_the_start_check(monkeypatch, auto_route, expected):
    off = SimpleNamespace(enabled=False, strategy="both")
    monkeypatch.setattr(supervisor.classifier_settings, "settings",
                        lambda: SimpleNamespace(auto_tier=off, auto_route=auto_route))
    assert supervisor._uses_laya([SimpleNamespace(role="specialist", enabled=True, llm=SimpleNamespace(provider="anthropic", strategy=None))]) is expected
