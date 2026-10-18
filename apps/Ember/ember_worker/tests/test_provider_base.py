from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from src.events import HistoryLine, TurnRequest
from src.providers.base import (
    SubprocessRunner,
    compose_prompt,
    folder_problem,
    resolve_executable,
    summarize_tool,
)


def request(history=(), prompt="do it") -> TurnRequest:
    return TurnRequest("t", 1, "C:/w", "ask", prompt, tuple(history))


def test_a_prompt_with_no_history_is_sent_as_is() -> None:
    assert compose_prompt(request()) == "do it"


def test_history_is_shown_before_the_new_message() -> None:
    text = compose_prompt(request([HistoryLine("user", "plan it"), HistoryLine("claude", "A then B")], "review"))

    assert text.endswith("New message for you:\nreview")
    assert "[user] plan it\n[claude] A then B" in text
    assert text.index("[user]") < text.index("New message")


def test_tool_summaries_prefer_the_meaningful_field() -> None:
    assert summarize_tool("Bash", {"command": "npm test", "timeout": 5}) == "npm test"
    assert summarize_tool("Edit", {"file_path": "a.py", "old_string": "x"}) == "a.py"
    assert summarize_tool("Grep", {"pattern": "foo"}) == "foo"
    assert summarize_tool("Odd", {"n": 1}) == '{"n": 1}'
    assert len(summarize_tool("Bash", {"command": "x" * 900})) == 200
    assert summarize_tool("Odd", {}) == "{}"


def test_a_folder_must_exist(tmp_path: Path) -> None:
    assert folder_problem(str(tmp_path)) is None
    assert folder_problem(str(tmp_path / "missing")) == f"The folder does not exist on this computer: {tmp_path / 'missing'}"
    assert folder_problem("") == "The folder is blank."


def test_resolve_executable_falls_back_to_the_bare_name() -> None:
    assert resolve_executable("definitely-not-installed-xyz") == "definitely-not-installed-xyz"
    assert Path(resolve_executable("python")).name.lower().startswith("python") or resolve_executable("python") == "python"


def test_the_subprocess_runner_returns_exit_code_and_output() -> None:
    runner = SubprocessRunner()

    code, out = asyncio.run(runner.run([sys.executable, "-c", "print('hi')"]))
    assert (code, out.strip()) == (0, "hi")

    code, _out = asyncio.run(runner.run([sys.executable, "-c", "raise SystemExit(3)"]))
    assert code == 3


def test_a_missing_program_is_exit_127() -> None:
    assert asyncio.run(SubprocessRunner().run(["definitely-not-installed-xyz"])) == (127, "")


def test_a_slow_program_is_stopped_with_exit_124() -> None:
    runner = SubprocessRunner(timeout_seconds=0.3)

    code, _out = asyncio.run(runner.run([sys.executable, "-c", "import time; time.sleep(5)"]))

    assert code == 124
