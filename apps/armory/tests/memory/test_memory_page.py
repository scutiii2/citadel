from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src.capabilities.memory import routes as memory_routes
from src.capabilities.memory.utils import memory_store

UID = "a" * 32
OTHER = "b" * 32
HEADERS = {"X-Internal-Token": "test-token"}
URL = f"/memory/owners/{UID}/notes"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_routes, "settings", SimpleNamespace(
        internal_api_token="test-token", memory_db_path=tmp_path / "memory.db"))
    monkeypatch.setattr(memory_routes, "_memory_online", lambda: True)
    app = Starlette()
    memory_routes.install_memory_routes(app)
    with TestClient(app) as client:
        yield client


def test_memory_page_crud_is_owner_scoped_and_updates_search(client):
    created = client.post(URL, headers=HEADERS, json={"text": "  likes   coffee "})
    assert created.status_code == 201
    note = created.json()
    assert note["text"] == "likes coffee"
    assert client.get(URL, headers=HEADERS).json() == [note]
    other = f"/memory/owners/{OTHER}/notes/{note['id']}"
    assert client.put(other, headers=HEADERS, json={"text": "tea", "expected_text": note["text"]}).status_code == 404
    assert client.delete(other, headers=HEADERS).status_code == 404
    edited = client.put(f"{URL}/{note['id']}", headers=HEADERS,
                        json={"text": "likes tea", "expected_text": note["text"]})
    assert edited.status_code == 200
    assert edited.json() == {**note, "text": "likes tea"}
    db = memory_routes.settings.memory_db_path
    assert memory_store.search(db, UID, "coffee") == []
    assert memory_store.search(db, UID, "tea")[0].id == note["id"]
    assert client.put(f"{URL}/{note['id']}", headers=HEADERS,
                      json={"text": "stale", "expected_text": note["text"]}).status_code == 409
    assert client.delete(f"{URL}/{note['id']}", headers=HEADERS).status_code == 204
    assert client.get(URL, headers=HEADERS).json() == []


def test_duplicates_do_not_destroy_or_replace_either_memory(client):
    first = client.post(URL, headers=HEADERS, json={"text": "coffee"}).json()
    second = client.post(URL, headers=HEADERS, json={"text": "tea"}).json()
    assert client.post(URL, headers=HEADERS, json={"text": "COFFEE"}).json() == first
    assert client.put(f"{URL}/{second['id']}", headers=HEADERS,
                      json={"text": "coffee", "expected_text": "tea"}).status_code == 409
    assert len(client.get(URL, headers=HEADERS).json()) == 2


@pytest.mark.parametrize("body", [{"text": " "}, {"text": "x" * 501}, {}, {"text": 4}, []])
def test_validation(client, body):
    assert client.post(URL, headers=HEADERS, json=body).status_code == 422


def test_internal_token_and_enabled_capability_required(client, monkeypatch):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"text": "x"}).status_code == 401
    monkeypatch.setattr(memory_routes, "_memory_online", lambda: False)
    assert client.get(URL, headers=HEADERS).status_code == 404


def test_list_returns_all_memories_instead_of_tool_limit(client):
    for i in range(12):
        assert client.post(URL, headers=HEADERS, json={"text": f"fact {i}"}).status_code == 201
    assert len(client.get(URL, headers=HEADERS).json()) == 12
