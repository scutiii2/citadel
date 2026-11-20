import pytest

from tests.auth_helpers import identity

def make(client, title="Tea notes", body="Likes tea.", **extra):
    answer = client.post("/brain/files", json={"title": title, "body": body, **extra})
    assert answer.status_code == 201, answer.text
    return answer.json()


def test_create_list_get_update_delete(client):
    file = make(client, tags=["Tea"], folder="drinks")
    assert file["source"] == "manual" and file["tags"] == ["tea"] and file["revision"] == 1 and file["warning"] is None
    listed = client.get("/brain/files").json()
    assert listed["folders"] == ["drinks"] and "body" not in listed["files"][0] and listed["files"][0]["chars"] == len("Likes tea.")
    assert client.get("/brain/files", params={"folder": "other"}).json()["files"] == []
    assert client.get(f"/brain/files/{file['id']}").json()["body"] == "Likes tea."
    changed = client.put(f"/brain/files/{file['id']}", json={"body": "Likes green tea.", "expected_revision": 1})
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    assert client.put(f"/brain/files/{file['id']}", json={"body": "x", "expected_revision": 1}).status_code == 412
    assert client.delete(f"/brain/files/{file['id']}").status_code == 204
    assert client.get(f"/brain/files/{file['id']}").status_code == 404


def test_bad_requests_are_refused_without_echoing_the_text(client):
    for body in ({"title": " ", "body": "secret-body"}, {"body": "secret-body"}, {"title": "t", "folder": "../secret-body"},
                 {"title": "t", "tags": "secret-body"}):
        answer = client.post("/brain/files", json=body)
        assert answer.status_code in (422,)
        assert "secret-body" not in answer.text
    assert client.get("/brain/files/not-an-id").status_code == 422
    assert client.put(f"/brain/files/{'a' * 32}", json={}).status_code in (404, 422)


def test_another_account_sees_nothing(client):
    other = identity(uid="u-2", username="bo", email="bo@example.com")
    file = make(client)
    assert client.get(f"/brain/files/{file['id']}", headers=other).status_code == 404
    assert client.get("/brain/files", headers=other).json() == {"files": [], "folders": []}
    assert client.get("/brain/search", params={"q": "tea"}, headers=other).json() == {"results": []}
    assert client.delete(f"/brain/files/{file['id']}", headers=other).status_code == 404


def test_search_and_summary(client):
    make(client, title="Tea", body="about tea")
    make(client, title="Coffee", body="about coffee")
    found = client.get("/brain/search", params={"q": "tea"}).json()["results"]
    assert [r["title"] for r in found] == ["Tea"] and found[0]["score"] > 0 and "snippet" in found[0] and "body" not in found[0]
    assert client.get("/brain/search", params={"q": ""}).status_code == 422
    assert client.get("/brain/search", params={"q": "tea", "limit": 99}).status_code == 422
    summary = client.get("/brain/summary").json()
    assert summary["files"] == 2 and summary["max_files"] == 500 and summary["max_record_chars"] == 20_000


def test_an_agent_written_file_warns_and_a_user_edit_can_be_reverted(client):
    import asyncio

    files = client.app.state.brain_files
    made = asyncio.run(files.create("u-1", title="Agent note", body="from the agent", actor="agent"))
    shown = client.get(f"/brain/files/{made.id}").json()
    assert shown["source"] == "automatic" and "break the agent" in shown["warning"]
    edited = client.put(f"/brain/files/{made.id}", json={"body": "user fix"}).json()
    assert edited["edited"] is True
    back = client.post(f"/brain/files/{made.id}/revert")
    assert back.status_code == 200 and back.json()["body"] == "from the agent" and back.json()["edited"] is False
    assert client.post(f"/brain/files/{made.id}/revert").status_code == 409


def test_letting_agents_edit_is_audited_without_text(client, platform):
    file = make(client, title="Private title", body="private body")
    changed = client.put(f"/brain/files/{file['id']}", json={"agent_editable": True})
    assert changed.json()["agent_editable"] is True
    assert platform.actions[-1][1] == "brain.agent_edit"
    assert "private" not in " ".join(platform.actions[-1])


def test_the_limits_come_from_the_settings(client):
    client.app.state.brain_files.limits = type(client.app.state.brain_files.limits)(max_record_chars=200, max_files=1)
    make(client, body="x")
    assert client.post("/brain/files", json={"title": "second", "body": "x"}).status_code == 409
    assert client.post("/brain/files", json={"title": "t", "body": "x" * 201}).status_code in (409, 422)


def test_storage_trouble_is_a_503_not_a_crash(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(client.app.state.brain_files, "list", broken)
    answer = client.get("/brain/files")
    assert answer.status_code == 503 and "disk gone" not in answer.text


def test_purging_an_account_removes_its_files(client):
    file = make(client)
    assert client.delete("/brain/accounts/u-1").status_code == 204
    assert client.get(f"/brain/files/{file['id']}").status_code == 404
    assert client.delete("/brain/accounts/..%2Fx").status_code in (404, 422)
    assert client.delete("/brain/accounts/u-9").status_code == 204


def test_the_brain_works_with_treasury_down(client, monkeypatch):
    async def unavailable(*args, **kwargs):
        from src.document_store import DbGatewayUnavailable

        raise DbGatewayUnavailable("down")

    for name in ("get", "put", "query", "create", "delete"):
        monkeypatch.setattr(client.app.state.store, name, unavailable)
    file = make(client)
    assert client.get(f"/brain/files/{file['id']}").status_code == 200

def test_health_survives_a_brain_root_that_cannot_hold_files(make_client, monkeypatch, tmp_path):
    unavailable = tmp_path / "occupied"
    unavailable.touch()
    monkeypatch.setenv("STRONGHOLD_BRAIN_ROOT", str(unavailable))
    client = make_client()
    assert client.get("/health").status_code == 200
    assert client.get("/brain/files").status_code == 503
    assert client.post("/brain/files", json={"title": "a", "body": "b"}).status_code == 503


def test_brain_query_text_is_removed_from_access_logs(client):
    import logging

    logger = logging.getLogger("uvicorn.access")
    record = logger.makeRecord(
        logger.name, logging.INFO, __file__, 1, "%s %s",
        ("GET", "/brain/files?folder=private-folder"), None,
    )
    for log_filter in logger.filters:
        log_filter.filter(record)
    assert record.getMessage() == "GET /brain/files?[redacted]"
