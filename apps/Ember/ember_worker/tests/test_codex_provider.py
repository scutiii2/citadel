from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport
from src.providers.codex import CodexEventParser, CodexPermissionMapper, CodexProvider, detect_codex_plan


def line(**event) -> str:
    return json.dumps(event)


def test_modes_map_to_codex_sandboxes() -> None:
    mapper = CodexPermissionMapper()

    assert [mapper.sandbox(m) for m in ("ask", "plan", "accept_edits", "full_auto")] == [
        "read-only", "read-only", "workspace-write", "danger-full-access",
    ]
    assert mapper.sandbox("surprise") == "read-only"


def test_the_parser_turns_a_normal_run_into_events() -> None:
    parser = CodexEventParser()
    stream = [
        line(type="thread.started", thread_id="abc"),
        line(type="turn.started"),
        line(type="item.completed", item={"id": "1", "type": "command_execution", "command": "npm test", "status": "completed"}),
        line(type="item.completed", item={"id": "2", "type": "file_change", "changes": [{"path": "a.py", "kind": "update"}, {"path": "b.py", "kind": "add"}]}),
        line(type="item.completed", item={"id": "3", "type": "agent_message", "text": "Fixed it."}),
        line(type="turn.completed", usage={"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5, "reasoning_output_tokens": 1}),
    ]

    events = [event for raw in stream for event in parser.feed(raw)]

    assert events == [
        ToolCall("shell", "npm test"),
        ToolCall("edit", "a.py, b.py"),
        TextDelta("Fixed it."),
        UsageReport(10, 5),
        Finished("Fixed it."),
    ]


def test_the_final_answer_is_the_last_agent_message() -> None:
    parser = CodexEventParser()
    for text in ("first", "second"):
        parser.feed(line(type="item.completed", item={"type": "agent_message", "text": text}))

    assert parser.feed(line(type="turn.completed")) == [Finished("second")]


def test_failures_and_errors() -> None:
    parser = CodexEventParser()

    assert parser.feed(line(type="error", message="Reconnecting 1/5")) == []
    assert parser.last_error == "Reconnecting 1/5"
    assert parser.feed(line(type="turn.failed", error={"message": "You hit your usage limit"})) == [
        Failed("You hit your usage limit")
    ]
    assert parser.feed(line(type="turn.failed")) == [Failed("Codex failed.")]


def test_noise_is_ignored() -> None:
    parser = CodexEventParser()

    for raw in ("", "not json", "[]", line(type="item.started", item={"type": "agent_message"}), line(type="mystery"),
                line(type="item.completed", item={"type": "reasoning", "text": "hmm"}), line(type="item.completed")):
        assert parser.feed(raw) == [], raw


def test_other_tool_like_items_are_named() -> None:
    parser = CodexEventParser()

    assert parser.feed(line(type="item.completed", item={"type": "web_search", "query": "python asyncio"})) == [
        ToolCall("web_search", "python asyncio")
    ]
    assert parser.feed(line(type="item.completed", item={"type": "mcp_tool_call", "tool": "read_page"})) == [
        ToolCall("mcp_tool_call", "read_page")
    ]


class FakeProcess:
    def __init__(self, lines, code=0, stderr="") -> None:
        self._lines, self._code, self._stderr = lines, code, stderr
        self.terminated = False
        self.release = None

    async def lines(self):
        for item in self._lines:
            if item is None:  # wait here until released (a long-running turn)
                self.release = asyncio.Event()
                await self.release.wait()
                continue
            yield item

    async def wait(self) -> int:
        return self._code

    async def stderr_text(self) -> str:
        return self._stderr

    def terminate(self) -> None:
        self.terminated = True
        if self.release is not None:
            self.release.set()


class FakeSpawner:
    def __init__(self, process) -> None:
        self.process, self.calls = process, []

    async def spawn(self, args, cwd, stdin_text):
        self.calls.append((args, cwd, stdin_text))
        return self.process


class FakeRunner:
    def __init__(self, code: int = 0) -> None:
        self.code, self.calls = code, []

    async def run(self, args):
        self.calls.append(args)
        return self.code, ""


class Gate:
    async def ask(self, tool, summary):
        raise AssertionError("Codex cannot ask")


def request(folder: str, mode: str = "accept_edits") -> TurnRequest:
    return TurnRequest("t1", 1, folder, mode, "go")


async def collect(provider, req):
    return [event async for event in provider.run_turn(req, Gate())]


def test_a_turn_runs_codex_exec_in_the_folder(tmp_path: Path) -> None:
    process = FakeProcess([
        line(type="item.completed", item={"type": "agent_message", "text": "Done"}),
        line(type="turn.completed", usage={"input_tokens": 1, "output_tokens": 2}),
    ])
    spawner = FakeSpawner(process)
    provider = CodexProvider(spawner, FakeRunner(), executable="codex")

    events = asyncio.run(collect(provider, request(str(tmp_path))))

    assert events == [TextDelta("Done"), UsageReport(1, 2), Finished("Done")]
    args, cwd, stdin_text = spawner.calls[0]
    assert args == ["codex", "exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", "-"]
    assert (cwd, stdin_text) == (str(tmp_path), "go")
    assert process.terminated is True  # always cleaned up


def test_a_missing_folder_fails_before_codex_starts(tmp_path: Path) -> None:
    spawner = FakeSpawner(FakeProcess([]))

    events = asyncio.run(collect(CodexProvider(spawner, FakeRunner()), request(str(tmp_path / "nope"))))

    assert len(events) == 1 and isinstance(events[0], Failed)
    assert spawner.calls == []


def test_codex_not_installed(tmp_path: Path) -> None:
    class Missing:
        async def spawn(self, args, cwd, stdin_text):
            raise FileNotFoundError("codex")

    events = asyncio.run(collect(CodexProvider(Missing(), FakeRunner()), request(str(tmp_path))))

    assert len(events) == 1 and "Could not start Codex" in events[0].message


def test_a_run_that_ends_without_an_answer_reports_why(tmp_path: Path) -> None:
    errored = FakeProcess([line(type="error", message="Not logged in")], code=1)
    silent = FakeProcess([], code=2, stderr="boom\n")
    bare = FakeProcess([], code=3)

    one = asyncio.run(collect(CodexProvider(FakeSpawner(errored), FakeRunner()), request(str(tmp_path))))
    two = asyncio.run(collect(CodexProvider(FakeSpawner(silent), FakeRunner()), request(str(tmp_path))))
    three = asyncio.run(collect(CodexProvider(FakeSpawner(bare), FakeRunner()), request(str(tmp_path))))

    assert one == [Failed("Not logged in")]
    assert two == [Failed("boom")]
    assert three == [Failed("Codex exited with code 3")]


def test_cancel_stops_the_process_and_the_turn_reports_it(tmp_path: Path) -> None:
    process = FakeProcess([None])  # runs until terminated
    provider = CodexProvider(FakeSpawner(process), FakeRunner())

    async def go():
        task = asyncio.create_task(collect(provider, request(str(tmp_path))))
        for _ in range(100):
            if "t1" in provider._processes:
                break
            await asyncio.sleep(0.01)
        await provider.cancel("t1")
        return await task

    assert asyncio.run(go()) == [Failed("cancelled")]
    assert process.terminated is True


def test_login_status_uses_the_exit_code() -> None:
    runner = FakeRunner(0)
    assert asyncio.run(CodexProvider(FakeSpawner(None), runner, executable="codex").is_logged_in()) is True
    assert runner.calls == [["codex", "login", "status"]]
    assert asyncio.run(CodexProvider(FakeSpawner(None), FakeRunner(1)).is_logged_in()) is False
    assert asyncio.run(CodexProvider(FakeSpawner(None), FakeRunner(127)).is_logged_in()) is False


def fake_jwt(claims: dict) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part(claims)}.sig"


def test_the_plan_is_read_from_the_id_token_claims(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"tokens": {"id_token": fake_jwt({"https://api.openai.com/auth": {"chatgpt_plan_type": "plus"}})}}),
        encoding="utf-8",
    )

    assert detect_codex_plan(auth) == "plus"
    assert asyncio.run(CodexProvider(FakeSpawner(None), FakeRunner(), codex_home=tmp_path).detect_plan()) == "plus"


def test_plan_detection_never_raises(tmp_path: Path) -> None:
    assert detect_codex_plan(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert detect_codex_plan(bad) is None
    for tokens in ({}, {"id_token": "nodots"}, {"id_token": "a.b.c"}, {"id_token": fake_jwt({"x": 1})},
                   {"id_token": fake_jwt({"https://api.openai.com/auth": {"chatgpt_plan_type": 5}})}):
        path = tmp_path / "t.json"
        path.write_text(json.dumps({"tokens": tokens}), encoding="utf-8")
        assert detect_codex_plan(path) is None
