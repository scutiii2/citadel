"""The internal Skills page routes: the only way a skill becomes active."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src import skill_routes
from src.services import skill_store as store

TOKEN = "shared-secret"
UID_A = "a" * 32
UID_B = "b" * 32
HEADERS = {"X-Internal-Token": TOKEN}


@pytest.fixture
def db(tmp_path):
    return tmp_path / "skills.db"


@pytest.fixture
def online(monkeypatch):
    state = {"on": True}
    monkeypatch.setattr(skill_routes, "_skills_online", lambda: state["on"])
    return state


@pytest.fixture
def client(monkeypatch, db, online):
    monkeypatch.setattr(skill_routes, "settings", SimpleNamespace(internal_api_token=TOKEN, skills_db_path=db))
    app = Starlette()
    skill_routes.install_skill_routes(app)
    with TestClient(app) as test_client:
        yield test_client


def propose(db, uid=UID_A, title="Restart an app"):
    return store.propose(db, uid, title, "an app is hung", "stop it, then start it").id


def url(uid=UID_A, tail=""):
    return f"/skills/owners/{uid}/skills{tail}"


def test_list_returns_every_status_of_that_owner_only(client, db):
    first = propose(db)
    store.set_status(db, UID_A, first, "active")
    propose(db, title="Second")
    propose(db, uid=UID_B, title="Other")

    skills = client.get(url(), headers=HEADERS).json()

    assert {(s["id"], s["status"]) for s in skills} == {(first, "active"), (2, "proposed")}


def test_approving_makes_a_skill_searchable(client, db):
    skill_id = propose(db)
    assert store.search(db, UID_A, "restart") == []

    response = client.put(url(tail=f"/{skill_id}/status"), headers=HEADERS, json={"status": "active"})

    assert response.status_code == 200 and response.json()["status"] == "active"
    assert [s.id for s in store.search(db, UID_A, "restart")] == [skill_id]


def test_retire_and_delete(client, db):
    skill_id = propose(db)
    client.put(url(tail=f"/{skill_id}/status"), headers=HEADERS, json={"status": "active"})
    assert client.put(url(tail=f"/{skill_id}/status"), headers=HEADERS, json={"status": "retired"}).json()["status"] == "retired"
    assert store.search(db, UID_A, "restart") == []
    assert client.delete(url(tail=f"/{skill_id}"), headers=HEADERS).status_code == 204
    assert store.list_skills(db, UID_A) == []
    assert client.delete(url(tail=f"/{skill_id}"), headers=HEADERS).status_code == 404


def test_another_owners_skill_is_not_found(client, db):
    skill_id = propose(db)
    assert client.put(url(UID_B, f"/{skill_id}/status"), headers=HEADERS, json={"status": "active"}).status_code == 404
    assert client.delete(url(UID_B, f"/{skill_id}"), headers=HEADERS).status_code == 404
    assert store.list_skills(db, UID_A)[0].status == "proposed"


def test_bad_status_and_bad_bodies_are_422(client, db):
    skill_id = propose(db)
    for body in ({"status": "banana"}, {}, {"status": 5}):
        assert client.put(url(tail=f"/{skill_id}/status"), headers=HEADERS, json=body).status_code == 422
    assert client.put(url(tail=f"/{skill_id}/status"), headers={**HEADERS, "content-type": "text/plain"}, content="x").status_code == 415


def test_the_active_cap_is_a_409(client, db, monkeypatch):
    monkeypatch.setattr(store, "MAX_ACTIVE", 1)
    first, second = propose(db), propose(db, title="Second")
    client.put(url(tail=f"/{first}/status"), headers=HEADERS, json={"status": "active"})
    response = client.put(url(tail=f"/{second}/status"), headers=HEADERS, json={"status": "active"})
    assert response.status_code == 409 and "Retire one first" in response.json()["error"]


@pytest.mark.parametrize("token", [None, "wrong"])
def test_a_missing_or_wrong_token_is_a_401_and_changes_nothing(client, db, token):
    skill_id = propose(db)
    headers = {"X-Internal-Token": token} if token else {}
    assert client.get(url(), headers=headers).status_code == 401
    assert client.put(url(tail=f"/{skill_id}/status"), headers=headers, json={"status": "active"}).status_code == 401
    assert store.list_skills(db, UID_A)[0].status == "proposed"


def test_an_unset_token_never_validates(client, db, monkeypatch):
    monkeypatch.setattr(skill_routes, "settings", SimpleNamespace(internal_api_token="", skills_db_path=db))
    assert client.get(url(), headers={"X-Internal-Token": ""}).status_code == 401


@pytest.mark.parametrize("uid", ["alice", "A" * 32, "a" * 31, "a" * 33])
def test_only_a_32_hex_uid_is_accepted(client, uid):
    assert client.get(url(uid), headers=HEADERS).status_code == 400


def test_everything_is_a_404_when_the_capability_is_offline(client, online, db):
    skill_id = propose(db)
    online["on"] = False
    assert client.get(url(), headers=HEADERS).status_code == 404
    assert client.put(url(tail=f"/{skill_id}/status"), headers=HEADERS, json={"status": "active"}).status_code == 404
    assert client.delete(f"/skills/owners/{UID_A}", headers=HEADERS).status_code == 404
    assert store.list_skills(db, UID_A)[0].status == "proposed"


def test_purge_removes_only_that_owner_and_hides_the_uid_in_logs(client, db, caplog):
    propose(db)
    propose(db, uid=UID_B, title="Other")

    caplog.set_level(logging.INFO, logger="uvicorn.access")
    response = client.delete(f"/skills/owners/{UID_A}", headers=HEADERS)
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "127.0.0.1", "DELETE", f"/skills/owners/{UID_A}/skills", "1.1", 200)

    assert response.status_code == 200 and response.json() == {"purged": 1}
    assert store.list_skills(db, UID_A) == [] and len(store.list_skills(db, UID_B)) == 1
    assert UID_A not in caplog.text and "/skills/owners/[redacted]" in caplog.text


def test_the_model_tools_cannot_reach_these_routes_or_set_status():
    import pathlib

    tool_source = (pathlib.Path(skill_routes.__file__).parent / "capabilities" / "skills" / "tool.py").read_text(encoding="utf-8")
    domain_source = (pathlib.Path(skill_routes.__file__).parent / "capabilities" / "skills" / "domain.py").read_text(encoding="utf-8")
    assert "set_status" not in tool_source and "set_status" not in domain_source
