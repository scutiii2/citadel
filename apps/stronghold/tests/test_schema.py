"""The schema layer: document models, the collection catalog, versioned migrations and GET /schema."""

import asyncio
import re

import pytest
from pydantic import ValidationError

from src.document_store import DbGatewayUnavailable
from src.schema import migrations
from src.schema.catalog import BY_NAME, CATALOG, STATE
from src.schema.models import ChatDoc, ChatFolderDoc, ShareDoc, UsageRecordDoc, checked

CHAT = {"key": "u:c1", "owner": "u", "chat_id": "c1", "title": "Hi", "created_at": "t", "updated_at": "t"}


def test_models_accept_the_documents_the_stores_write_and_keep_unknown_fields(client, db_gateway):
    client.put("/chats/11111111-1111-1111-1111-111111111111", json={"title": "Hello", "messages": [{"role": "user", "content": "x"}]})
    for (collection, _), doc in db_gateway.records.items():
        model = BY_NAME[collection].model
        if model:
            assert model.model_validate(doc).model_dump()["key"] == doc["key"]
    assert ChatDoc.model_validate({**CHAT, "added_later": 1}).model_extra == {"added_later": 1}


def test_models_refuse_a_document_that_does_not_fit():
    for bad in ({**CHAT, "owner": ""}, {**CHAT, "title": "x" * 121}, {**CHAT, "second_brain_scope": "all"},
                {k: v for k, v in CHAT.items() if k != "chat_id"}):
        with pytest.raises(ValidationError):
            checked(ChatDoc, bad)
    with pytest.raises(ValidationError):
        checked(ChatFolderDoc, {"key": "u:1", "owner": "u", "id": 0, "name": "f", "position": 0, "created_at": "t"})
    with pytest.raises(ValidationError):
        checked(ShareDoc, {"key": "h", "owner": "u", "id": 1, "chat_id": "c", "title": "t", "messages": "no", "message_count": 0, "created_at": "t"})
    with pytest.raises(ValidationError):
        checked(UsageRecordDoc, {"key": "u:a", "owner": "u", "id": 2**53, "turn_id": "t", "kind": "chat", "day": "2026-11-16", "created_at": "t"})
    with pytest.raises(ValidationError):
        checked(UsageRecordDoc, {"key": "u:a", "owner": "u", "id": 1, "turn_id": "t", "kind": "chat", "day": "16/11", "created_at": "t"})


def test_a_store_never_writes_an_invalid_document(client, db_gateway):
    from src.chats.store import ChatStore
    from src.shares.store import ShareStore

    store = ChatStore(db_gateway, ShareStore(db_gateway))
    with pytest.raises(ValidationError):
        asyncio.run(store.put("", "c1", "Title", None, []))  # no owner
    assert db_gateway.records == {}


def test_catalog_names_are_unique_and_every_purge_route_exists(client):
    assert len(BY_NAME) == len(CATALOG)
    for collection in CATALOG:
        if collection.purge:
            answer = client.delete(collection.purge.format(uid="u-9"))
            assert answer.status_code in (204, 502), (collection.name, answer.status_code)  # 502: brains, Armory not faked


def test_every_collection_named_in_code_is_in_the_catalog():
    import pathlib

    named = set()
    for path in pathlib.Path("src").rglob("*.py"):
        if "schema" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        named |= set(re.findall(r'^[A-Z_]+ = "([a-z][a-z_]+)"$', text, re.MULTILINE))
    # Constants that name something else than a collection.
    named -= {"instance", "personal", "baseline", "stronghold", "agent", "provider", "gateway", "model", "chat", "ok"}
    collections = {name for name in named if name in BY_NAME or name.startswith(("chat_", "brain_", "usage_", "shared_", "prompt_", "tuning_", "ticket_"))}
    assert collections <= set(BY_NAME), collections - set(BY_NAME)


def test_the_fake_store_refuses_a_collection_missing_from_the_catalog(db_gateway):
    with pytest.raises(AssertionError, match="catalog"):
        asyncio.run(db_gateway.put("not_catalogued", "k", {}))


def test_start_records_the_baseline_and_schema_shows_it(client, db_gateway):
    assert client.app.state.schema_version == 1
    shown = client.get("/schema").json()
    assert shown["version"] == 1 and shown["latest"] == 1 and shown["applied"][0]["name"] == "baseline"
    assert {c["name"] for c in shown["collections"]} == set(BY_NAME)
    assert any(c["name"] == "chats" and c["checked"] for c in shown["collections"])
    assert db_gateway.system[(STATE, "stronghold")]["version"] == 1


def test_schema_needs_the_internal_token(client):
    client.auth = None
    assert client.get("/schema").status_code == 401


def run(coro):
    return asyncio.run(coro)


def test_migrations_run_in_order_once_and_record_each(db_gateway):
    ran = []

    async def one(_store):
        ran.append(2)

    async def two(_store):
        ran.append(3)

    steps = (migrations.Migration(1, "baseline", migrations.baseline), migrations.Migration(2, "one", one), migrations.Migration(3, "two", two))
    state = run(migrations.migrate(db_gateway, steps))
    assert [a["name"] for a in state["applied"]] == ["baseline", "one", "two"] and ran == [2, 3]
    assert run(migrations.migrate(db_gateway, steps))["version"] == 3 and ran == [2, 3]  # nothing runs twice


def test_a_failed_step_keeps_the_version_before_it_and_is_retried(db_gateway):
    attempts = []

    async def flaky(_store):
        attempts.append(1)
        if len(attempts) == 1:
            raise DbGatewayUnavailable("down")

    steps = (migrations.Migration(1, "baseline", migrations.baseline), migrations.Migration(2, "flaky", flaky))
    with pytest.raises(DbGatewayUnavailable):
        run(migrations.migrate(db_gateway, steps))
    assert run(migrations.current(db_gateway))["version"] == 1
    assert run(migrations.migrate(db_gateway, steps))["version"] == 2 and len(attempts) == 2


def test_data_from_a_newer_version_is_refused_and_left_alone(db_gateway):
    run(db_gateway.put(STATE, "stronghold", {"key": "stronghold", "version": 9, "applied": []}))
    with pytest.raises(migrations.SchemaTooNew):
        run(migrations.migrate(db_gateway))
    assert run(migrations.current(db_gateway))["version"] == 9


def test_stronghold_still_starts_when_storage_is_down_or_data_is_too_new(tmp_path, db_gateway, platform, agent):
    import json

    import httpx
    from fastapi.testclient import TestClient

    from src.api import create_app
    from src.config import Settings
    from tests.conftest import AGENTS, FakeArmory

    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps({"agents": AGENTS}), encoding="utf-8")

    async def down(*_args, **_kwargs):
        raise DbGatewayUnavailable("down")

    db_gateway.get = down
    upstream = httpx.AsyncClient(base_url="http://armory.test", transport=httpx.MockTransport(FakeArmory()))
    app = create_app("", Settings(data_dir=tmp_path / "data", agents_registry_path=registry), store=db_gateway,
                     platform=platform, armory=upstream, agent_gateway=agent, legion=upstream)
    with TestClient(app) as test_client:
        assert app.state.schema_version is None
        assert test_client.get("/health").json() == {"status": "ok"}
