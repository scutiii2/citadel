import asyncio
import functools
import inspect
from datetime import timedelta

import pytest

from src.db import Database, utcnow
from src.services.outside_clients import OutsideClientError, OutsideClients


def with_db(test):
    """Run an async test body on a fresh in-memory database (no pytest-asyncio here)."""

    async def body(*args, **kwargs):
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_tables()
        try:
            await test(database, *args, **kwargs)
        finally:
            await database.engine.dispose()

    @functools.wraps(test)
    def wrapper(*args, **kwargs):
        asyncio.run(body(*args, **kwargs))

    params = [p for n, p in inspect.signature(test).parameters.items() if n != "db"]
    wrapper.__signature__ = inspect.Signature(params)
    return wrapper


async def make(db, **extra):
    async with db.sessions() as session:
        clients = OutsideClients(session)
        args = dict(name="Docs bot", services=["legion"], budget_tokens=1000)
        client, key = await clients.create(**{**args, **extra})
        await session.commit()
        return client.id, key


@with_db
async def test_a_client_is_created_with_a_key_shown_once_and_only_its_hash_kept(db):
    client_id, key = await make(db)
    assert key.startswith("ock_") and len(key) > 40
    async with db.sessions() as session:
        client = await OutsideClients(session).get(client_id)
    assert client.key_hash != key and key not in (client.key_hash, client.key_prefix)
    assert client.key_prefix == key[:8] and client.uid.startswith("oc_") and len(client.uid) == 15
    assert client.enabled is True and client.rate_per_minute == 10 and client.budget_days == 30


@with_db
async def test_the_key_finds_its_client_and_nothing_else_does(db):
    client_id, key = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        assert (await clients.authenticate(key)).id == client_id
        assert await clients.authenticate(key + "x") is None
        assert await clients.authenticate("") is None
        assert await clients.authenticate("Bearer " + key) is None


@with_db
async def test_rotating_the_key_ends_the_old_one(db):
    client_id, old = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        _client, new = await clients.rotate_key(client_id)
        await session.commit()
        assert await clients.authenticate(old) is None
        assert (await clients.authenticate(new)).id == client_id


@pytest.mark.parametrize("extra, message", [
    ({"name": " "}, "name"), ({"name": "x" * 61}, "name"), ({"name": "bad/name"}, "name"),
    ({"services": ["stronghold"]}, "service"), ({"services": []}, "service"), ({"services": ["legion", "legion"]}, "service"),
    ({"rate_per_minute": 0}, "rate"), ({"rate_per_minute": 601}, "rate"),
    ({"budget_tokens": 0}, "budget"), ({"budget_tokens": 100_000_001}, "budget"), ({"budget_days": 0}, "days"), ({"budget_days": 367}, "days"),
    ({"ip_allow": ["not-an-address"]}, "address"),
])
@with_db
async def test_a_bad_record_is_refused_in_words(db, extra, message):
    with pytest.raises(OutsideClientError, match=message):
        await make(db, **extra)


@with_db
async def test_names_are_unique_ignoring_case(db):
    await make(db)
    with pytest.raises(OutsideClientError, match="already"):
        await make(db, name="docs BOT")


@with_db
async def test_update_validates_and_a_disabled_client_still_authenticates_but_is_marked(db):
    client_id, key = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        updated = await clients.update(client_id, enabled=False, ip_allow=["203.0.113.0/24"], budget_tokens=5)
        await session.commit()
        assert updated.enabled is False and updated.ip_allow == ["203.0.113.0/24"]
        assert (await clients.authenticate(key)).enabled is False
        with pytest.raises(OutsideClientError, match="budget"):
            await clients.update(client_id, budget_tokens=0)
        with pytest.raises(OutsideClientError, match="Unknown"):
            await clients.update(client_id, uid="oc_hacked")


@with_db
async def test_the_budget_counts_only_calls_inside_the_window(db):
    client_id, _ = await make(db, budget_tokens=100, budget_days=2)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        client = await clients.get(client_id)
        await clients.record(client, service="legion", action="call", status=200, tokens=40, ip="1.1.1.1")
        await clients.record(client, service="legion", action="refused", reason="rate", status=429, ip="1.1.1.1")
        await session.commit()
        used, reset = await clients.spent(client)
        assert used == 40 and reset is not None and reset > utcnow()
        later = utcnow() + timedelta(days=3)
        assert await clients.spent(client, now=later) == (0, None)


@with_db
async def test_events_are_newest_first_page_by_id_and_hold_no_text(db):
    client_id, _ = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        client = await clients.get(client_id)
        for number in range(5):
            await clients.record(client, service="legion", action="call", status=200, tokens=number, ip="1.1.1.1")
        await session.commit()
        first = await clients.events(client_id, limit=2)
        assert [e.tokens for e in first] == [4, 3]
        rest = await clients.events(client_id, limit=10, before_id=first[-1].id)
        assert [e.tokens for e in rest] == [2, 1, 0]
        assert {"question", "answer", "text"}.isdisjoint(vars(first[0]))


@with_db
async def test_deleting_a_client_deletes_its_events(db):
    client_id, _ = await make(db)
    async with db.sessions() as session:
        clients = OutsideClients(session)
        client = await clients.get(client_id)
        await clients.record(client, service="legion", action="call", status=200, tokens=1, ip="1.1.1.1")
        await session.commit()
        assert await clients.delete(client_id) is True
        await session.commit()
        assert await clients.events(client_id) == [] and await clients.get(client_id) is None
        assert await clients.delete(client_id) is False
