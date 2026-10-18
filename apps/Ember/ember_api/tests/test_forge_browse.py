from __future__ import annotations

import asyncio

import pytest

from src.services.forge.browse import BrowseInProgress, BrowseTimeout, FolderBrowser, WorkerOffline
from src.services.forge.connections import WorkerConnection, WorkerRegistry
from src.services.forge.protocol import BrowseResult
from tests.forge_support import FakeTransport, settle


def setup(timeout: float = 5.0):
    registry = WorkerRegistry()
    transport = FakeTransport()
    registry.register(WorkerConnection(1, transport))
    return FolderBrowser(registry, timeout), transport


def test_the_worker_is_asked_and_the_chosen_folder_comes_back() -> None:
    async def scenario() -> None:
        browser, transport = setup()
        task = asyncio.create_task(browser.pick(1, "C:/start"))
        await settle(lambda: transport.sent)

        frame = transport.sent[0]
        assert (frame["type"], frame["start"]) == ("browse", "C:/start")
        browser.on_result(1, BrowseResult(request_id=frame["request_id"], path="C:/work/site"))

        assert await task == "C:/work/site"

    asyncio.run(scenario())


def test_cancelling_the_dialog_gives_none() -> None:
    async def scenario() -> None:
        browser, transport = setup()
        task = asyncio.create_task(browser.pick(1))
        await settle(lambda: transport.sent)

        browser.on_result(1, BrowseResult(request_id=transport.sent[0]["request_id"], path=None))

        assert await task is None

    asyncio.run(scenario())


def test_an_offline_worker_is_refused() -> None:
    async def scenario() -> None:
        with pytest.raises(WorkerOffline):
            await FolderBrowser(WorkerRegistry()).pick(7)

    asyncio.run(scenario())


def test_only_one_dialog_per_worker() -> None:
    async def scenario() -> None:
        browser, transport = setup()
        first = asyncio.create_task(browser.pick(1))
        await settle(lambda: transport.sent)

        with pytest.raises(BrowseInProgress):
            await browser.pick(1)

        browser.on_result(1, BrowseResult(request_id=transport.sent[0]["request_id"], path="C:/a"))
        assert await first == "C:/a"
        second = asyncio.create_task(browser.pick(1))  # free again
        await settle(lambda: len(transport.sent) == 2)
        browser.on_result(1, BrowseResult(request_id=transport.sent[1]["request_id"], path="C:/b"))
        assert await second == "C:/b"

    asyncio.run(scenario())


def test_a_wrong_or_late_answer_is_ignored() -> None:
    async def scenario() -> None:
        browser, transport = setup()
        task = asyncio.create_task(browser.pick(1))
        await settle(lambda: transport.sent)
        real = transport.sent[0]["request_id"]

        browser.on_result(1, BrowseResult(request_id="not-it", path="C:/x"))
        browser.on_result(2, BrowseResult(request_id=real, path="C:/y"))  # another worker's socket
        assert not task.done()
        browser.on_result(1, BrowseResult(request_id=real, path="C:/z"))
        assert await task == "C:/z"
        browser.on_result(1, BrowseResult(request_id=real, path="C:/late"))  # nothing waits now

    asyncio.run(scenario())


def test_no_answer_in_time_is_a_timeout_and_frees_the_worker() -> None:
    async def scenario() -> None:
        browser, transport = setup(timeout=0.05)

        with pytest.raises(BrowseTimeout):
            await browser.pick(1)
        again = asyncio.create_task(browser.pick(1))  # not stuck as "in progress"
        await settle(lambda: len(transport.sent) == 2)
        browser.on_result(1, BrowseResult(request_id=transport.sent[1]["request_id"], path="C:/ok"))
        assert await again == "C:/ok"

    asyncio.run(scenario())


def test_a_worker_that_drops_while_the_dialog_is_open_is_offline() -> None:
    async def scenario() -> None:
        browser, transport = setup()
        task = asyncio.create_task(browser.pick(1))
        await settle(lambda: transport.sent)

        browser.on_disconnected(1)

        with pytest.raises(WorkerOffline):
            await task

    asyncio.run(scenario())
