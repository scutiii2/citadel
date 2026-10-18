from __future__ import annotations

import asyncio

from src.services.forge.approvals import PendingPermission, PermissionBroker

PENDING = PendingPermission(request_id="r1", group_id=1, worker_id=5, turn_id="t1")


def test_resolve_returns_the_request_once() -> None:
    async def go():
        broker = PermissionBroker(on_timeout=lambda p: asyncio.sleep(0), timeout_seconds=5)
        broker.open(PENDING)
        first = broker.resolve(1, "r1")
        second = broker.resolve(1, "r1")
        broker.close()
        return first, second

    assert asyncio.run(go()) == (PENDING, None)


def test_a_request_of_another_group_cannot_be_resolved() -> None:
    async def go():
        broker = PermissionBroker(on_timeout=lambda p: asyncio.sleep(0), timeout_seconds=5)
        broker.open(PENDING)
        wrong = broker.resolve(2, "r1")
        right = broker.resolve(1, "r1")
        broker.close()
        return wrong, right

    assert asyncio.run(go()) == (None, PENDING)


def test_an_unanswered_request_times_out_once() -> None:
    async def go():
        expired: list[PendingPermission] = []

        async def on_timeout(pending: PendingPermission) -> None:
            expired.append(pending)

        broker = PermissionBroker(on_timeout, timeout_seconds=0.02)
        broker.open(PENDING)
        await asyncio.sleep(0.1)
        return expired, broker.resolve(1, "r1")

    expired, late = asyncio.run(go())
    assert expired == [PENDING] and late is None


def test_an_answered_request_never_times_out() -> None:
    async def go():
        expired: list[PendingPermission] = []

        async def on_timeout(pending: PendingPermission) -> None:
            expired.append(pending)

        broker = PermissionBroker(on_timeout, timeout_seconds=0.02)
        broker.open(PENDING)
        broker.resolve(1, "r1")
        await asyncio.sleep(0.1)
        return expired

    assert asyncio.run(go()) == []


def test_discarding_a_turn_drops_its_requests_without_timing_out() -> None:
    async def go():
        expired: list[PendingPermission] = []

        async def on_timeout(pending: PendingPermission) -> None:
            expired.append(pending)

        broker = PermissionBroker(on_timeout, timeout_seconds=0.02)
        other = PendingPermission("r2", 1, 5, "t2")
        broker.open(PENDING)
        broker.open(other)
        dropped = broker.discard_turn("t1")
        await asyncio.sleep(0.1)
        return dropped, expired

    dropped, expired = asyncio.run(go())
    assert dropped == [PENDING] and expired == [PendingPermission("r2", 1, 5, "t2")]
