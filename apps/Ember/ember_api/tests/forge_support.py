"""Shared setup for the Forge tests: a real SQLite database with two accounts (alice = 1, bob = 2)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from src.db import Database
from src.models import Account, ForgeGroup, ForgeGroupWorker, ForgeWorker

T = TypeVar("T")


class ForgeEnv:
    def __init__(self, tmp_path: Path) -> None:
        self.database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'forge.db').as_posix()}")

    async def setup(self) -> None:
        await self.database.create_tables()
        async with self.database.sessions() as session:
            for name in ("alice", "bob"):
                session.add(Account(username=name, email=f"{name}@example.com", password_hash="x"))
            await session.commit()

    async def add_worker(
        self, account_id: int = 1, provider: str = "claude", label: str | None = None, plan: str | None = "Max"
    ) -> ForgeWorker:
        async with self.database.sessions() as session:
            worker = ForgeWorker(
                account_id=account_id,
                provider=provider,
                label=label or provider,
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                reported_plan=plan,
            )
            session.add(worker)
            await session.commit()
            return worker

    async def allow(self, provider: str, *plans: str) -> None:
        from src.services.forge.plans import ClaudePlanPolicy, CodexPlanPolicy

        async with self.database.sessions() as session:
            policy = ClaudePlanPolicy(session) if provider == "claude" else CodexPlanPolicy(session)
            await policy.set_allowed(list(plans))

    async def add_group(
        self, account_id: int = 1, workers: tuple[ForgeWorker, ...] | list[ForgeWorker] = (), mode: str = "ask", relay: bool = False
    ) -> ForgeGroup:
        async with self.database.sessions() as session:
            group = ForgeGroup(account_id=account_id, title="Build", mode=mode, relay=relay)
            session.add(group)
            await session.flush()
            for worker in workers:
                session.add(ForgeGroupWorker(group_id=group.id, worker_id=worker.id, folder="C:/work"))
            await session.commit()
            return group


def run(tmp_path: Path, scenario: Callable[[ForgeEnv], Awaitable[T]]) -> T:
    """Runs `scenario(env)` against a fresh database."""
    env = ForgeEnv(tmp_path)

    async def go() -> T:
        await env.setup()
        try:
            return await scenario(env)
        finally:
            await env.database.dispose()

    return asyncio.run(go())


class FakeTransport:
    """Stands in for a worker's WebSocket: records frames sent and the close code."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed: int | None = None

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self, code: int = 1000) -> None:
        self.closed = code


async def settle(predicate: Callable[[], object], timeout: float = 3.0) -> None:
    """Waits (without blocking the loop) until `predicate()` is truthy."""
    waited = 0.0
    while not predicate():
        if waited >= timeout:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.01)
        waited += 0.01


async def settle_async(predicate: Callable[[], Awaitable[object]], timeout: float = 3.0) -> None:
    """Like settle, for a predicate that is a coroutine function."""
    waited = 0.0
    while not await predicate():
        if waited >= timeout:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.01)
        waited += 0.01
