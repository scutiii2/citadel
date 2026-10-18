from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest
from src.providers.claude import ClaudePermissionMapper, ClaudeProvider


class FakeRunner:
    def __init__(self, code: int = 0, out: str = "") -> None:
        self.code, self.out, self.calls = code, out, []

    async def run(self, args):
        self.calls.append(args)
        return self.code, self.out


class FakeSession:
    def __init__(self, script) -> None:
        self._script = script
        self.interrupted = False

    async def events(self):
        for item in self._script:
            if callable(item):
                await item()
            else:
                yield item

    async def interrupt(self) -> None:
        self.interrupted = True


class FakeFactory:
    def __init__(self, script=(), fail: Exception | None = None) -> None:
        self.script, self.fail = script, fail
        self.opened = []
        self.session = FakeSession(script)

    @asynccontextmanager
    async def open(self, request, permission_mode, can_use):
        if self.fail:
            raise self.fail
        self.opened.append((request, permission_mode, can_use))
        yield self.session


class Gate:
    def __init__(self, answer: bool = True) -> None:
        self.answer, self.asked = answer, []

    async def ask(self, tool: str, summary: str) -> bool:
        self.asked.append((tool, summary))
        return self.answer


def req(folder: str, mode: str = "ask") -> TurnRequest:
    return TurnRequest("t1", 1, folder, mode, "go")


async def collect(provider, request, gate=None):
    return [event async for event in provider.run_turn(request, gate or Gate())]


def test_modes_map_to_claude_permission_modes() -> None:
    mapper = ClaudePermissionMapper()

    assert [mapper.permission_mode(m) for m in ("ask", "accept_edits", "plan", "full_auto")] == [
        "default", "acceptEdits", "plan", "bypassPermissions",
    ]
    assert mapper.permission_mode("surprise") == "plan"  # unknown modes get the safest one


def test_a_turn_streams_the_sessions_events(tmp_path: Path) -> None:
    factory = FakeFactory([TextDelta("Hi"), ToolCall("Bash", "ls"), Finished("Hi there")])
    provider = ClaudeProvider(factory, FakeRunner())

    events = asyncio.run(collect(provider, req(str(tmp_path), mode="accept_edits")))

    assert events == [TextDelta("Hi"), ToolCall("Bash", "ls"), Finished("Hi there")]
    request, mode, _can_use = factory.opened[0]
    assert (request.turn_id, mode) == ("t1", "acceptEdits")


def test_the_permission_callback_asks_the_gate(tmp_path: Path) -> None:
    factory = FakeFactory([Finished("ok")])
    gate = Gate(answer=False)
    provider = ClaudeProvider(factory, FakeRunner())

    async def go():
        await collect(provider, req(str(tmp_path)), gate)
        _request, _mode, can_use = factory.opened[0]
        return await can_use("Bash", "rm -rf build")

    assert asyncio.run(go()) is False
    assert gate.asked == [("Bash", "rm -rf build")]


def test_a_missing_folder_fails_before_the_cli_starts(tmp_path: Path) -> None:
    factory = FakeFactory([Finished("never")])

    events = asyncio.run(collect(ClaudeProvider(factory, FakeRunner()), req(str(tmp_path / "nope"))))

    assert len(events) == 1 and isinstance(events[0], Failed) and "does not exist" in events[0].message
    assert factory.opened == []


def test_a_cli_crash_becomes_a_failed_event(tmp_path: Path) -> None:
    factory = FakeFactory(fail=RuntimeError("CLI exited with code 1"))

    events = asyncio.run(collect(ClaudeProvider(factory, FakeRunner()), req(str(tmp_path))))

    assert events == [Failed("Claude failed: CLI exited with code 1")]


def test_cancel_interrupts_the_running_session(tmp_path: Path) -> None:
    provider = ClaudeProvider(FakeFactory(), FakeRunner())

    async def go():
        release = asyncio.Event()

        async def wait_for_release():
            await release.wait()

        provider._factory.session = FakeSession([wait_for_release, Finished("late")])
        task = asyncio.create_task(collect(provider, req(str(tmp_path))))
        for _ in range(100):
            if "t1" in provider._sessions:
                break
            await asyncio.sleep(0.01)
        await provider.cancel("t1")
        interrupted = provider._sessions["t1"].interrupted
        release.set()
        await task
        return interrupted, "t1" in provider._sessions

    assert asyncio.run(go()) == (True, False)  # interrupted, and forgotten once the turn ended


def test_cancelling_an_unknown_turn_does_nothing() -> None:
    asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner()).cancel("nope"))


def test_login_and_plan_come_from_claude_auth_status() -> None:
    status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"})
    runner = FakeRunner(0, status)
    provider = ClaudeProvider(FakeFactory(), runner, executable="claude")

    assert asyncio.run(provider.is_logged_in()) is True
    assert asyncio.run(provider.detect_plan()) == "max"
    assert runner.calls[0] == ["claude", "auth", "status"]


def test_logged_out_missing_or_unreadable_status() -> None:
    out = json.dumps({"loggedIn": False, "authMethod": "none"})
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(1, out)).is_logged_in()) is False
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(1, out)).detect_plan()) is None
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(127, "")).is_logged_in()) is False
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(0, "not json")).detect_plan()) is None
    odd = json.dumps({"loggedIn": True, "subscriptionType": 5})
    assert asyncio.run(ClaudeProvider(FakeFactory(), FakeRunner(0, odd)).detect_plan()) is None
