from tests.auth_helpers import identity

WRITER = {"chat.use", "brain.global.write"}
READER = {"chat.use"}


def as_writer(platform, uid="u-1"):
    platform.granted[uid] = WRITER


def test_everyone_reads_and_only_a_writer_writes(client, platform):
    platform.granted["u-1"] = READER
    assert client.get("/brain/global/files").json() == {"files": [], "folders": []}
    assert client.post("/brain/global/files", json={"title": "Rules", "body": "be kind"}).status_code == 403
    assert client.put("/brain/global/files/" + "a" * 32, json={"body": "x"}).status_code == 403
    assert client.delete("/brain/global/files/" + "a" * 32).status_code == 403
    assert client.get("/brain/global/skills/all").status_code == 403
    as_writer(platform)
    made = client.post("/brain/global/files", json={"title": "Rules", "body": "be kind", "tags": ["house"], "folder": "policy"})
    assert made.status_code == 201 and made.json()["source"] == "manual"
    file_id = made.json()["id"]
    platform.granted["u-2"] = READER
    other = identity(uid="u-2", username="bo", email="bo@example.com")
    assert client.get(f"/brain/global/files/{file_id}", headers=other).json()["body"] == "be kind"
    assert [r["title"] for r in client.get("/brain/global/files", headers=other).json()["files"]] == ["Rules"]
    found = client.get("/brain/global/search", params={"q": "kind"}, headers=other).json()["results"]
    assert [r["id"] for r in found] == [file_id]
    assert "Do not put private data" in client.get("/brain/global/summary", headers=other).json()["notice"]
    changed = client.put(f"/brain/global/files/{file_id}", json={"body": "be very kind", "expected_revision": 1})
    assert changed.status_code == 200 and changed.json()["revision"] == 2 and "notice" in changed.json()
    assert client.delete(f"/brain/global/files/{file_id}").status_code == 204
    assert client.get(f"/brain/global/files/{file_id}", headers=other).status_code == 404
    assert ("u-1", "brain.global_write", "Changed the global brain") in platform.actions


def test_the_global_brain_is_separate_from_a_personal_brain(client, platform):
    as_writer(platform)
    client.post("/brain/global/files", json={"title": "Global", "body": "g"})
    client.post("/brain/files", json={"title": "Mine", "body": "m"})
    assert [r["title"] for r in client.get("/brain/files").json()["files"]] == ["Mine"]
    assert [r["title"] for r in client.get("/brain/global/files").json()["files"]] == ["Global"]


def test_global_skills_reach_readers_only_when_active(client, platform):
    import asyncio

    as_writer(platform)
    store = client.app.state.global_brain.skills
    skill, _ = asyncio.run(store.propose("global", "Restart an app", "hung", "stop, start", ""))
    assert client.get("/brain/global/skills").json() == []
    assert [s["status"] for s in client.get("/brain/global/skills/all").json()] == ["proposed"]
    assert client.put(f"/brain/global/skills/{skill.id}/status", json={"status": "active"}).status_code == 200
    assert [s["id"] for s in client.get("/brain/global/skills").json()] == [skill.id]
    edited = client.put(f"/brain/global/skills/{skill.id}", json={"title": "Reboot", "when_to_use": "hung", "steps": "kill it"})
    assert edited.status_code == 200 and edited.json()["title"] == "Reboot"
    platform.granted["u-1"] = READER
    assert client.put(f"/brain/global/skills/{skill.id}/status", json={"status": "retired"}).status_code == 403
    assert client.delete(f"/brain/global/skills/{skill.id}").status_code == 403
    as_writer(platform)
    assert client.delete(f"/brain/global/skills/{skill.id}").status_code == 204
    assert client.get("/brain/global/skills/all").json() == []


def test_an_inactive_or_unknown_account_cannot_write(client, platform):
    platform.granted["u-1"] = None
    assert client.post("/brain/global/files", json={"title": "x", "body": "y"}).status_code == 403
