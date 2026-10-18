from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from src.models import ForgeWorker
from src.services.forge.workers import (
    MAX_WORKERS_PER_ACCOUNT,
    InvalidWorkerLabel,
    WorkerAuthenticator,
    WorkerLabelTaken,
    WorkerLimitError,
    WorkerNotFound,
    WorkerPairingService,
    clean_label,
    hash_token,
)
from tests.forge_support import run


def test_create_returns_the_token_once_and_stores_only_its_hash(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            created = await WorkerPairingService(session, 1).create("claude", " Claude ")
            assert created.token.startswith("ft_") and len(created.token) > 30
            assert created.worker.label == "claude"
            stored = await session.scalar(select(ForgeWorker))
            assert stored.token_hash == hash_token(created.token)
            assert created.token not in (stored.token_hash, stored.label)

    run(tmp_path, scenario)


def test_labels_are_handles_unique_per_account(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            mine = WorkerPairingService(session, 1)
            await mine.create("claude", "claude")
            with pytest.raises(WorkerLabelTaken):
                await mine.create("codex", "CLAUDE")
            await WorkerPairingService(session, 2).create("claude", "claude")  # another account may reuse it

    run(tmp_path, scenario)


@pytest.mark.parametrize("label", ["", "a b", "x" * 25, "ü", "@x"])
def test_bad_labels_are_refused(label: str) -> None:
    with pytest.raises(InvalidWorkerLabel):
        clean_label(label)


def test_an_unknown_provider_is_refused(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            with pytest.raises(ValueError):
                await WorkerPairingService(session, 1).create("gemini", "gem")

    run(tmp_path, scenario)


def test_the_number_of_workers_is_limited(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            service = WorkerPairingService(session, 1)
            for index in range(MAX_WORKERS_PER_ACCOUNT):
                await service.create("claude", f"w{index}")
            with pytest.raises(WorkerLimitError):
                await service.create("claude", "one-more")

    run(tmp_path, scenario)


def test_another_accounts_worker_looks_missing(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            theirs = (await WorkerPairingService(session, 2).create("claude", "claude")).worker
            mine = WorkerPairingService(session, 1)
            assert await mine.list() == []
            with pytest.raises(WorkerNotFound):
                await mine.get(theirs.id)
            with pytest.raises(WorkerNotFound):
                await mine.delete(theirs.id)

    run(tmp_path, scenario)


def test_delete_removes_the_worker_and_its_token_stops_working(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            service = WorkerPairingService(session, 1)
            created = await service.create("claude", "claude")
            auth = WorkerAuthenticator(session)
            assert (await auth.authenticate(created.token)).id == created.worker.id
            await service.delete(created.worker.id)
            assert await auth.authenticate(created.token) is None

    run(tmp_path, scenario)


def test_authenticate_rejects_wrong_and_malformed_tokens(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            await WorkerPairingService(session, 1).create("claude", "claude")
            auth = WorkerAuthenticator(session)
            assert await auth.authenticate("ft_wrong") is None
            assert await auth.authenticate("") is None
            assert await auth.authenticate("nope") is None

    run(tmp_path, scenario)


def test_hello_records_the_plan_and_the_time(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            worker = (await WorkerPairingService(session, 1).create("claude", "claude")).worker
            auth = WorkerAuthenticator(session)
            await auth.record_hello(worker.id, "  Max  ")
            stored = await session.scalar(select(ForgeWorker).execution_options(populate_existing=True))
            assert stored.reported_plan == "Max" and stored.last_seen is not None
            await auth.record_hello(worker.id, None)
            stored = await session.scalar(select(ForgeWorker).execution_options(populate_existing=True))
            assert stored.reported_plan is None

    run(tmp_path, scenario)
