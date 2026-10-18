"""What every provider shares: the Provider interface, how a turn becomes a prompt, and small
helpers for running the CLIs' own commands."""

from __future__ import annotations

import asyncio
import json
import shutil
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from src.events import TurnEvent, TurnRequest

_SUMMARY_KEYS = ("command", "file_path", "path", "pattern", "url", "query", "description")


class PermissionGate(Protocol):
    """Asks the user (through the Forge page) whether a tool may run."""

    async def ask(self, tool: str, summary: str) -> bool: ...


class CommandRunner(Protocol):
    """Runs a short CLI command (a login or status check) and returns (exit code, stdout)."""

    async def run(self, args: list[str]) -> tuple[int, str]: ...


class SubprocessRunner:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds

    async def run(self, args: list[str]) -> tuple[int, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
        except (FileNotFoundError, PermissionError):
            return 127, ""
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), self._timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return 124, ""
        return process.returncode or 0, stdout.decode("utf-8", errors="replace")


class Provider(ABC):
    """One CLI (Claude Code or Codex) behind a common face."""

    name: str

    @abstractmethod
    async def detect_plan(self) -> str | None:
        """The subscription plan the CLI is logged in with, if it can tell."""

    @abstractmethod
    async def is_logged_in(self) -> bool: ...

    @abstractmethod
    def run_turn(self, request: TurnRequest, gate: PermissionGate) -> AsyncIterator[TurnEvent]:
        """Runs one turn and yields its events; the last is exactly one Finished or Failed."""

    @abstractmethod
    async def cancel(self, turn_id: str) -> None:
        """Asks the turn to stop; run_turn then ends with Failed."""


def compose_prompt(request: TurnRequest) -> str:
    """The message the CLI gets: the new prompt, with what the worker missed shown first."""
    if not request.history:
        return request.prompt
    lines = "\n".join(f"[{line.sender}] {line.text}" for line in request.history)
    return (
        "You are one of several AI workers in a group chat with the user. "
        "Here is what was said since you last took part:\n"
        f"{lines}\n\nNew message for you:\n{request.prompt}"
    )


def summarize_tool(name: str, data: dict, limit: int = 200) -> str:
    """One short line saying what a tool call is about (a command, a file, a pattern)."""
    for key in _SUMMARY_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value[:limit]
    return json.dumps(data, ensure_ascii=False, default=str)[:limit]


def folder_problem(folder: str) -> str | None:
    if not folder.strip():
        return "The folder is blank."
    if not Path(folder).is_dir():
        return f"The folder does not exist on this computer: {folder}"
    return None


def resolve_executable(name: str) -> str:
    """The full path of a program on PATH (Windows needs it for .cmd shims), else the bare name."""
    return shutil.which(name) or name
