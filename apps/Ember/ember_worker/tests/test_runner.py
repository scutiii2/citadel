from __future__ import annotations

import asyncio

import pytest

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport
from src.providers.base import Provider
from src.runner import TurnRunner


class ScriptedProvider(Provider):
    name = "scripted"

    def __init__(self, script) -> None:
        self.script = script
        self.cancelled = []
        self.gate_answers = []

    async def detect_plan(self):
        return None

    async def is_logged_in(self):
        return True

    async def run_turn(self, request, gate):
        for item in self.script:
            if callable(item):
                result = await item(gate)
                if result is not None:
                    self.gate_answers.append(result)
            else:
                yield item

    async def cancel(self, turn_id):
        self.cancelled.append(turn_id)


class Wire:
    def __init__(self) -> None:
        self.frames = []

    async def send(self, frame: dict) -> None:
        self.frames.append(frame)

    def types(self, turn_id: str = "t1") -> list[str]:
        return [f["type"] for f in self.frames if f.get("turn_id") == turn_id]


def request(turn_id: str = "t1") -> TurnRequest:
    return TurnRequest(turn_id, 1, ".", "ask", "go")


async def idle(runner: TurnRunner, timeout: float = 3.0) -> None:
    waited = 0.0
    while runner.active_turns():
        assert waited < timeout, "turn did not end"
        await asyncio.sleep(0.01)
        waited += 0.01


def test_events_become_frames_in_order() -> None:
    async def go():
        wire = Wire()
        provider = ScriptedProvider([TextDelta("Hel"), ToolCall("Bash", "ls"), UsageReport(3, 4), Finished("Hello")])
        runner = TurnRunner(provider, wire.send)
        runner.start(request())
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [
        {"type": "delta", "turn_id": "t1", "text": "Hel"},
        {"type": "tool", "turn_id": "t1", "name": "Bash", "summary": "ls"},
        {"type": "usage", "turn_id": "t1", "input_tokens": 3, "output_tokens": 4},
        {"type": "turn_done", "turn_id": "t1", "text": "Hello"},
    ]


def test_a_failure_is_one_turn_error() -> None:
    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([Failed("not logged in"), TextDelta("ignored")]), wire.send)
        runner.start(request())
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [{"type": "turn_error", "turn_id": "t1", "message": "not logged in"}]


def test_a_provider_that_ends_silently_still_gets_a_terminal_frame() -> None:
    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([TextDelta("partial")]), wire.send)
        runner.start(request())
        await idle(runner)
        return wire.types()

    assert asyncio.run(go()) == ["delta", "turn_error"]


def test_an_exception_becomes_a_turn_error() -> None:
    async def boom(gate):
        raise RuntimeError("kaput")

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([boom]), wire.send)
        runner.start(request())
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [{"type": "turn_error", "turn_id": "t1", "message": "kaput"}]


def test_a_permission_question_waits_for_the_reply() -> None:
    async def ask(gate):
        return await gate.ask("Bash", "rm -rf build")

    async def go():
        wire = Wire()
        provider = ScriptedProvider([ask, Finished("ok")])
        runner = TurnRunner(provider, wire.send)
        runner.start(request())
        for _ in range(100):
            if any(f["type"] == "permission_request" for f in wire.frames):
                break
            await asyncio.sleep(0.01)
        asked = next(f for f in wire.frames if f["type"] == "permission_request")
        assert (asked["turn_id"], asked["tool"], asked["summary"]) == ("t1", "Bash", "rm -rf build")
        assert "turn_done" not in wire.types()  # still waiting
        runner.permission_reply(asked["request_id"], True)
        await idle(runner)
        return provider.gate_answers, wire.types()

    answers, types = asyncio.run(go())
    assert answers == [True] and types == ["permission_request", "turn_done"]


def test_a_reply_for_an_unknown_question_is_ignored() -> None:
    TurnRunner(ScriptedProvider([]), Wire().send).permission_reply("nope", True)


def test_cancel_denies_open_questions_and_tells_the_provider() -> None:
    async def ask(gate):
        return await gate.ask("Bash", "x")

    async def go():
        wire = Wire()
        provider = ScriptedProvider([ask, Failed("stopped")])
        runner = TurnRunner(provider, wire.send)
        runner.start(request())
        for _ in range(100):
            if any(f["type"] == "permission_request" for f in wire.frames):
                break
            await asyncio.sleep(0.01)
        await runner.cancel("t1")
        await idle(runner)
        return provider.gate_answers, provider.cancelled, wire.frames[-1]

    answers, cancelled, last = asyncio.run(go())
    assert answers == [False] and cancelled == ["t1"]
    assert last == {"type": "turn_error", "turn_id": "t1", "message": "cancelled"}


def test_a_turn_that_ignores_cancel_is_stopped_after_the_grace_time() -> None:
    async def stubborn(gate):
        await asyncio.sleep(30)

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([stubborn]), wire.send, cancel_grace=0.05)
        runner.start(request())
        await asyncio.sleep(0.02)
        await runner.cancel("t1")
        await idle(runner)
        return wire.frames

    assert asyncio.run(go()) == [{"type": "turn_error", "turn_id": "t1", "message": "cancelled"}]


def test_cancelling_an_unknown_turn_does_nothing() -> None:
    asyncio.run(TurnRunner(ScriptedProvider([]), Wire().send).cancel("nope"))


def test_two_turns_can_run_at_once() -> None:
    async def slow(gate):
        await asyncio.sleep(0.05)

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([slow, Finished("x")]), wire.send)
        runner.start(request("a"))
        runner.start(request("b"))
        started = runner.active_turns()
        await idle(runner)
        return started, wire.types("a"), wire.types("b")

    started, a, b = asyncio.run(go())
    assert started == {"a", "b"} and a == ["turn_done"] and b == ["turn_done"]


def test_starting_the_same_turn_twice_runs_it_once() -> None:
    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([Finished("x")]), wire.send)
        runner.start(request())
        runner.start(request())
        await idle(runner)
        return wire.types()

    assert asyncio.run(go()) == ["turn_done"]


def test_shutdown_stops_everything() -> None:
    async def forever(gate):
        await asyncio.sleep(60)

    async def go():
        wire = Wire()
        runner = TurnRunner(ScriptedProvider([forever]), wire.send)
        runner.start(request())
        await asyncio.sleep(0.02)
        await runner.shutdown()
        return runner.active_turns()

    assert asyncio.run(go()) == set()


def test_the_registry_builds_known_providers_only() -> None:
    from src.providers.registry import build_provider

    assert build_provider("claude").name == "claude"
    assert build_provider("codex").name == "codex"
    with pytest.raises(ValueError):
        build_provider("gemini")
