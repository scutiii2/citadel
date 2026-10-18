"""Claude Code behind the Provider interface. The Agent SDK itself sits behind
ClaudeSessionFactory (see claude_sdk.py), so everything here is tested with fakes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from src.events import Failed, TurnEvent, TurnRequest
from src.providers.base import CommandRunner, PermissionGate, Provider, folder_problem, resolve_executable

CanUse = Callable[[str, str], Awaitable[bool]]


class ClaudePermissionMapper:
    """Forge's group modes as Claude Code permission modes."""

    _MODES = {"ask": "default", "accept_edits": "acceptEdits", "plan": "plan", "full_auto": "bypassPermissions"}

    def permission_mode(self, mode: str) -> str:
        return self._MODES.get(mode, "plan")


class ClaudeSession(Protocol):
    """One turn's conversation with the Claude CLI."""

    def events(self) -> AsyncIterator[TurnEvent]: ...

    async def interrupt(self) -> None: ...


class ClaudeSessionFactory(Protocol):
    def open(
        self, request: TurnRequest, permission_mode: str, can_use: CanUse
    ) -> AbstractAsyncContextManager[ClaudeSession]: ...


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(
        self,
        factory: ClaudeSessionFactory,
        runner: CommandRunner,
        mapper: ClaudePermissionMapper | None = None,
        executable: str | None = None,
    ) -> None:
        self._factory = factory
        self._runner = runner
        self._mapper = mapper or ClaudePermissionMapper()
        self._executable = executable or resolve_executable("claude")
        self._sessions: dict[str, ClaudeSession] = {}

    async def is_logged_in(self) -> bool:
        return bool((await self._auth_status()).get("loggedIn"))

    async def detect_plan(self) -> str | None:
        plan = (await self._auth_status()).get("subscriptionType")
        return plan if isinstance(plan, str) and plan.strip() else None

    async def _auth_status(self) -> dict:
        _code, out = await self._runner.run([self._executable, "auth", "status"])
        try:
            data = json.loads(out)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    async def run_turn(self, request: TurnRequest, gate: PermissionGate) -> AsyncIterator[TurnEvent]:
        problem = folder_problem(request.folder)
        if problem is not None:
            yield Failed(problem)
            return

        async def can_use(tool: str, summary: str) -> bool:
            return await gate.ask(tool, summary)

        try:
            async with self._factory.open(request, self._mapper.permission_mode(request.mode), can_use) as session:
                self._sessions[request.turn_id] = session
                async for event in session.events():
                    yield event
        except Exception as error:
            yield Failed(f"Claude failed: {error}")
        finally:
            self._sessions.pop(request.turn_id, None)

    async def cancel(self, turn_id: str) -> None:
        session = self._sessions.get(turn_id)
        if session is not None:
            await session.interrupt()
