"""OutsideGuard: key, service, client IP list, rate and budget, in that order; refusals of a known client are audited."""

import pytest

from src.services.outside_clients import OutsideClients
from src.services.outside_guard import ClientRateLimiter, OutsideGuard, OutsideRefused
from tests.test_outside_clients import with_db


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


async def setup(db, **extra):
    async with db.sessions() as session:
        client, key = await OutsideClients(session).create(
            **{**dict(name="bot", services=["legion"], budget_tokens=100, rate_per_minute=2), **extra})
        await session.commit()
        return client.id, key


def guard():
    clock = Clock()
    return OutsideGuard(ClientRateLimiter(clock=clock)), clock


async def admit(db, the_guard, key, service="legion", ip="203.0.113.5"):
    async with db.sessions() as session:
        try:
            return await the_guard.admit(OutsideClients(session), key, service, ip)
        finally:
            await session.commit()


async def refusal(db, the_guard, key, **kwargs):
    with pytest.raises(OutsideRefused) as caught:
        await admit(db, the_guard, key, **kwargs)
    return caught.value


@with_db
async def test_a_good_key_is_admitted(db):
    _id, key = await setup(db)
    the_guard, _ = guard()
    assert (await admit(db, the_guard, key)).name == "bot"


@pytest.mark.parametrize("key", [None, "", "nope", "ock_unknown"])
@with_db
async def test_a_missing_or_wrong_key_is_401_with_one_message(db, key):
    await setup(db)
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code, refused.message) == (401, "invalid_key", "Invalid or missing key.")


@with_db
async def test_a_disabled_client_looks_like_a_wrong_key_but_is_audited(db):
    client_id, key = await setup(db)
    async with db.sessions() as session:
        await OutsideClients(session).update(client_id, enabled=False)
        await session.commit()
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.message) == (401, "Invalid or missing key.")
    async with db.sessions() as session:
        events = await OutsideClients(session).events(client_id)
    assert [(e.action, e.reason) for e in events] == [("refused", "disabled")]


@with_db
async def test_a_service_the_client_may_not_use_is_403(db):
    _id, key = await setup(db)
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key, service="stronghold")
    assert (refused.status, refused.code) == (403, "service_not_allowed")


@with_db
async def test_the_clients_own_ip_list_is_enforced(db):
    _id, key = await setup(db, ip_allow=["203.0.113.0/24"])
    the_guard, _ = guard()
    await admit(db, the_guard, key, ip="203.0.113.7")
    refused = await refusal(db, the_guard, key, ip="198.51.100.1")
    assert (refused.status, refused.code) == (403, "ip_not_allowed")


@with_db
async def test_the_rate_limit_answers_429_with_retry_after_and_recovers(db):
    _id, key = await setup(db)
    the_guard, clock = guard()
    await admit(db, the_guard, key)
    await admit(db, the_guard, key)
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code) == (429, "rate_limited") and 1 <= refused.retry_after <= 60
    clock.now = 61.0
    await admit(db, the_guard, key)


@with_db
async def test_an_exhausted_budget_answers_429_with_the_time_it_resets(db):
    client_id, key = await setup(db, budget_tokens=50)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        await clients.record(await clients.get(client_id), service="legion", action="call", status=200, tokens=50, ip="1.1.1.1")
        await session.commit()
    the_guard, _ = guard()
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code) == (429, "budget_exhausted") and refused.retry_after > 0


@with_db
async def test_when_the_budget_cannot_be_read_the_call_is_refused(db, monkeypatch):
    _id, key = await setup(db)
    the_guard, _ = guard()

    async def broken(self, client, now=None):
        raise RuntimeError("database is down")

    monkeypatch.setattr(OutsideClients, "spent", broken)
    refused = await refusal(db, the_guard, key)
    assert (refused.status, refused.code) == (503, "budget_unavailable")


@with_db
async def test_every_refusal_of_a_known_client_leaves_an_event_without_text(db):
    client_id, key = await setup(db)
    the_guard, _ = guard()
    await refusal(db, the_guard, key, service="stronghold")
    async with db.sessions() as session:
        events = await OutsideClients(session).events(client_id)
    assert [(e.action, e.reason, e.status, e.tokens) for e in events] == [("refused", "service_not_allowed", 403, 0)]


def test_the_limiter_tracks_at_most_1000_clients():
    clock = Clock()
    limiter = ClientRateLimiter(clock=clock)
    for client_id in range(1001):
        assert limiter.retry_after(client_id, 1) is None
    assert len(limiter._calls) <= 1000
