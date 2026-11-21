"""Account deletion purges legacy notes from Treasury."""

import asyncio

from fastapi.testclient import TestClient

from src.document_store import DbGatewayUnavailable
from src.notes.store import NotesService
from tests.conftest import FakeDbGateway


def test_purging_an_account_removes_only_its_notes(client: TestClient, db_gateway: FakeDbGateway) -> None:
    async def seed_notes() -> None:
        alice = NotesService(db_gateway, "alice")
        await alice.create("a1", "milk")
        await alice.create("a2", "milk")
        await NotesService(db_gateway, "bob").create("b1", "milk")

    asyncio.run(seed_notes())

    assert client.delete("/notes/accounts/alice").status_code == 204

    assert [d["title"] for d in db_gateway.records.values()] == ["b1"]


def test_a_purge_that_cannot_reach_storage_says_so(client: TestClient, db_gateway: FakeDbGateway, monkeypatch) -> None:
    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("db_gateway is not reachable")

    monkeypatch.setattr(db_gateway, "query", down)

    assert client.delete("/notes/accounts/someone").status_code == 503
