"""Codex behind the Provider interface, using `codex exec --json`. That mode is
non-interactive, so Codex cannot ask the user: the group mode picks the sandbox up front."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.events import Failed, Finished, TextDelta, ToolCall, TurnEvent, TurnRequest, UsageReport
from src.providers.base import (
    CommandRunner,
    PermissionGate,
    Provider,
    compose_prompt,
    folder_problem,
    resolve_executable,
)

_AUTH_CLAIM = "https://api.openai.com/auth"


class CodexPermissionMapper:
    """Forge's group modes as Codex sandboxes (read-only is also what Ask and Plan get)."""

    _SANDBOXES = {
        "ask": "read-only",
        "plan": "read-only",
        "accept_edits": "workspace-write",
        "full_auto": "danger-full-access",
    }

    def sandbox(self, mode: str) -> str:
        return self._SANDBOXES.get(mode, "read-only")


class CodexEventParser:
    """Reads the JSON lines `codex exec --json` prints, one at a time."""

    def __init__(self) -> None:
        self._last_message = ""
        self.last_error: str | None = None

    def feed(self, raw: str) -> list[TurnEvent]:
        try:
            event = json.loads(raw)
        except ValueError:
            return []
        if not isinstance(event, dict):
            return []
        kind = event.get("type")
        if kind == "item.completed":
            return self._item(event.get("item"))
        if kind == "turn.completed":
            events: list[TurnEvent] = []
            usage = event.get("usage")
            if isinstance(usage, dict):
                events.append(UsageReport(int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)))
            events.append(Finished(self._last_message))
            return events
        if kind == "turn.failed":
            error = event.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            return [Failed(message if isinstance(message, str) and message else "Codex failed.")]
        if kind == "error":
            message = event.get("message")
            if isinstance(message, str) and message:
                self.last_error = message
        return []

    def _item(self, item: object) -> list[TurnEvent]:
        if not isinstance(item, dict):
            return []
        kind = item.get("type")
        if kind == "agent_message" and isinstance(item.get("text"), str):
            self._last_message = item["text"]
            return [TextDelta(item["text"])]
        if kind == "command_execution":
            return [ToolCall("shell", str(item.get("command", "")))]
        if kind == "file_change":
            changes = item.get("changes")
            paths = [c.get("path") for c in changes if isinstance(c, dict)] if isinstance(changes, list) else []
            if not paths and isinstance(item.get("path"), str):
                paths = [item["path"]]
            return [ToolCall("edit", ", ".join(p for p in paths if isinstance(p, str)))]
        if kind in ("mcp_tool_call", "web_search"):
            detail = item.get("query") or item.get("tool") or ""
            return [ToolCall(kind, str(detail))]
        return []


class CodexProcess(Protocol):
    def lines(self) -> AsyncIterator[str]: ...

    async def wait(self) -> int: ...

    async def stderr_text(self) -> str: ...

    def terminate(self) -> None: ...


class CodexSpawner(Protocol):
    async def spawn(self, args: list[str], cwd: str, stdin_text: str) -> CodexProcess: ...


def detect_codex_plan(auth_path: Path) -> str | None:
    """The ChatGPT plan named in the logged-in user's id token, read from the file on this computer.
    Best effort: any problem gives None. The token is decoded in memory and never kept or printed."""
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
        token = data["tokens"]["id_token"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        plan = claims[_AUTH_CLAIM]["chatgpt_plan_type"]
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    return plan if isinstance(plan, str) and plan.strip() else None


class CodexProvider(Provider):
    name = "codex"

    def __init__(
        self,
        spawner: CodexSpawner,
        runner: CommandRunner,
        mapper: CodexPermissionMapper | None = None,
        codex_home: Path | None = None,
        executable: str | None = None,
    ) -> None:
        self._spawner = spawner
        self._runner = runner
        self._mapper = mapper or CodexPermissionMapper()
        self._codex_home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        self._executable = executable or resolve_executable("codex")
        self._processes: dict[str, CodexProcess] = {}
        self._cancelled: set[str] = set()

    async def is_logged_in(self) -> bool:
        code, _out = await self._runner.run([self._executable, "login", "status"])
        return code == 0

    async def detect_plan(self) -> str | None:
        return detect_codex_plan(self._codex_home / "auth.json")

    async def run_turn(self, request: TurnRequest, gate: PermissionGate) -> AsyncIterator[TurnEvent]:
        problem = folder_problem(request.folder)
        if problem is not None:
            yield Failed(problem)
            return
        args = [
            self._executable, "exec", "--json", "--sandbox", self._mapper.sandbox(request.mode),
            "--skip-git-repo-check", "-",
        ]
        try:
            process = await self._spawner.spawn(args, request.folder, compose_prompt(request))
        except OSError as error:
            yield Failed(f"Could not start Codex ({error}). Is the codex CLI installed?")
            return
        self._processes[request.turn_id] = process
        parser = CodexEventParser()
        terminal = False
        try:
            async for raw in process.lines():
                for event in parser.feed(raw):
                    terminal = terminal or isinstance(event, (Finished, Failed))
                    yield event
            code = await process.wait()
            if not terminal:
                if request.turn_id in self._cancelled:
                    yield Failed("cancelled")
                else:
                    detail = parser.last_error or (await process.stderr_text()).strip()[-500:]
                    yield Failed(detail or f"Codex exited with code {code}")
        finally:
            self._processes.pop(request.turn_id, None)
            self._cancelled.discard(request.turn_id)
            process.terminate()

    async def cancel(self, turn_id: str) -> None:
        process = self._processes.get(turn_id)
        if process is not None:
            self._cancelled.add(turn_id)
            process.terminate()
