"""/brains: connections, permissions asked per request, Armory's resolve call, browsing, review and purge."""

import json

import httpx
from src.citadel_auth import ServiceAuth
from tests import auth_helpers
from tests.auth_helpers import requester

PERSONAL = "/brains/connections/personal"
INSTANCE = "/brains/connections/instance"
SAVE = {"label": "Mine", "endpoint": "https://vault.lan", "api_key": "private-brain-key", "allow_write": True}


def armory_auth():
    return ServiceAuth(auth_helpers.stack["armory"], "stronghold")


def armory_ok(armory):
    armory.handler = lambda request: httpx.Response(200, json={"ok": True})


def test_connection_saves_without_returning_the_key_and_rejects_stale_and_bad_input(client, armory, platform):
    armory_ok(armory)
    saved = client.put(PERSONAL, json=SAVE)
    assert saved.status_code == 200, saved.text
    assert "private-brain-key" not in saved.text and saved.json()["credential_configured"]
    assert client.get(PERSONAL).json()["revision"] == 1
    assert any(r.url.path == "/brains/operation" and json.loads(r.content)["operation"] == "retire" for r in armory.requests)
    assert ("u-1", "brain.connection_save", "scope=personal; revision=1") in platform.actions
    assert client.put(PERSONAL, json=SAVE).status_code == 409  # stale revision
    bad = client.put(PERSONAL, json={**SAVE, "endpoint": "http://bad", "expected_revision": 1})
    assert bad.status_code == 422 and "private-brain-key" not in bad.text


def test_save_still_works_when_armory_is_down(client, armory):
    armory.handler = lambda request: httpx.Response(503)
    assert client.put(PERSONAL, json=SAVE).status_code == 200


def test_members_manage_personal_but_not_the_instance_brain(client, platform):
    platform.granted["u-1"] = {"chat.use"}
    assert client.get(PERSONAL).status_code == 200
    assert client.get(INSTANCE).status_code == 404
    assert client.put(INSTANCE, json=SAVE).status_code == 404
    assert client.get("/brains/destinations").status_code == 200


def test_unusable_account_is_refused_and_a_permission_change_applies_at_once(client, platform):
    platform.granted["u-1"] = None
    assert client.get(PERSONAL).status_code == 403
    platform.granted["u-1"] = {"chat.use", "settings.manage"}
    assert client.get(PERSONAL).status_code == 200
    platform.granted["u-1"] = None
    assert client.get(PERSONAL).status_code == 403
    platform.granted["u-1"] = {"settings.manage"}
    assert client.get("/brains/promotions").status_code == 403  # needs chat.use


def test_instance_resolver_authorizes_without_returning_a_connection(client, platform):
    platform.granted["u-1"] = {"chat.use"}
    body = {"scope": "instance", "operation": "read"}
    assert client.post("/brains/resolve", json=body).status_code == 403
    answer = client.post("/brains/resolve", json=body, auth=armory_auth())
    assert answer.json() == {"scope": "instance", "authorized": True}
    assert client.post("/brains/resolve", json={**body, "operation": "write"}, auth=armory_auth()).status_code == 403
    manage = {**body, "operation": "manage"}
    assert client.post("/brains/resolve", json=manage, auth=armory_auth()).status_code == 403
    platform.granted["u-1"] = {"settings.manage"}
    assert client.post("/brains/resolve", json=manage, auth=armory_auth()).json() == answer.json()


def test_migration_exports_the_latest_committed_revision_and_removes_it_after_ack(client, db_gateway):
    import asyncio

    from src.citadel_auth.brain_migration import acknowledgement, challenge, unseal

    path = "/brains/instance-migration"
    armory = auth_helpers.stack["armory"]
    key = "fixture-legacy-credential"
    base = {"id": "instance", "scope": "instance", "owner": "", "label": "Shared",
            "endpoint": "https://vault.lan", "folder": "Published", "enabled": True,
            "allow_write": True, "updated_at": "2026-11-18T00:00:00+00:00",
            "credential": client.app.state.box.encrypt_map({"api_key": key})}
    older = {**base, "revision": 1, "generation": "older"}
    current = {**base, "revision": 2, "generation": "committed"}
    db_gateway.records["brain_connections", "instance"] = older
    db_gateway.records["brain_connection_revisions", "instance:1"] = older
    db_gateway.records["brain_connection_revisions", "instance:2"] = current

    private, proof = challenge(armory)
    assert client.post(path, json={"proof": proof}).status_code == 403
    exported = client.post(path, json={"proof": proof}, auth=armory_auth())
    assert exported.status_code == 200 and key not in exported.text
    old = asyncio.run(unseal(armory, private, proof, exported.json()))
    assert (old["api_key"], old["revision"], old["generation"]) == (key, 2, "committed")
    assert client.post(path, json={"proof": proof}, auth=armory_auth()).status_code == 403

    def ack(generation):
        return client.post(f"{path}/ack", json={"proof": acknowledgement(armory, 2, generation)},
                           auth=armory_auth())

    assert ack("different").status_code == 409
    assert db_gateway.records["brain_connection_revisions", "instance:2"] == current
    assert ack("committed").status_code == 204
    assert ack("committed").status_code == 204
    assert all(not name.startswith("instance") for _, name in db_gateway.records)


def test_platform_down_is_a_503(client, platform):
    async def down(uid):
        from src.platform import PlatformError

        raise PlatformError("Portcullis is unreachable")

    platform.permissions = down
    assert client.get(PERSONAL).status_code == 503


def test_resolve_hands_armory_the_credential_and_checks_publish(client, armory, platform):
    armory_ok(armory)
    client.put(PERSONAL, json=SAVE)
    snapshot = client.post("/brains/resolve", json={"scope": "personal", "operation": "write"}, auth=armory_auth())
    assert snapshot.status_code == 200 and snapshot.json()["api_key"] == "private-brain-key"
    platform.granted["u-1"] = {"chat.use"}
    assert client.post("/brains/resolve", json={"scope": "instance", "operation": "write"}, auth=armory_auth()).status_code == 403
    assert client.post("/brains/resolve", json={"scope": "personal", "operation": "read"}, auth=armory_auth()).status_code == 200
    platform.granted["u-1"] = None
    assert client.post("/brains/resolve", json={"scope": "personal", "operation": "read"}, auth=armory_auth()).status_code == 403
    platform.granted["u-1"] = {"chat.use"}
    assert client.post("/brains/resolve", json={"scope": "personal", "operation": "nuke"}, auth=armory_auth()).status_code == 422


def test_resolve_needs_the_internal_token(client):
    client.auth = None
    assert client.post("/brains/resolve", json={"scope": "personal", "operation": "read"}).status_code == 401


def test_writable_follows_connection_and_publish_permission(client, armory, platform):
    armory_ok(armory)
    assert client.get("/brains/writable/personal").json() == {"writable": False}
    client.put(PERSONAL, json=SAVE)
    assert client.get("/brains/writable/personal").json() == {"writable": True}
    shared = {"id": "instance", "scope": "instance", "label": "Shared", "folder": "Inbox", "enabled": True,
              "revision": 2, "generation": "imported", "status": "configured", "writable": True}
    armory.handler = lambda request: httpx.Response(200, json=shared)
    assert client.get("/brains/writable/instance").json() == {"writable": True}
    assert armory.requests[-1].url.path == "/brains/destination"
    assert client.get("/brains/destinations").json()[-1] == shared
    platform.granted["u-1"] = {"chat.use"}
    assert client.get("/brains/writable/instance").json() == {"writable": False}


def test_browse_passes_the_account_to_armory(client, armory):
    armory.handler = lambda request: httpx.Response(200, json={"items": []})
    answer = client.post("/brains/browse", json={"scope": "both", "operation": "list"})
    assert answer.status_code == 200
    sent = armory.requests[-1]
    assert sent.url.path == "/brains/operation" and requester(sent)["sub"] == "u-1"
    assert json.loads(sent.content)["scope"] == "both"
    armory.handler = lambda request: httpx.Response(500)
    assert client.post("/brains/browse", json={"operation": "list"}).status_code == 503


def test_test_connection_sends_armory_a_candidate_with_the_key(client, armory):
    armory_ok(armory)
    assert client.post(f"{PERSONAL}/test", json=SAVE).status_code == 200
    assert json.loads(armory.requests[-1].content)["candidate"]["api_key"] == "private-brain-key"


def make_note(client, title="Private procedure"):
    return client.post("/notes", json={"title": title, "body": "Durable private instructions"}).json()


def test_ai_review_consent_usage_dismiss_and_invalid_output(client, armory, agent):
    armory_ok(armory)
    client.put(PERSONAL, json=SAVE)
    note = make_note(client)
    payload = {"note_ids": [note["id"]]}
    assert client.post("/brains/suggestions/review", json=payload).status_code == 400
    assert not agent.interprets
    payload["explicit_private"] = [note["id"]]
    agent.summary = json.dumps({"suggestions": [{"note_id": note["id"], "reason": "Reusable procedure", "title": "Procedure",
        "folder": "Inbox", "tags": [], "scope": "personal", "draft": "# Procedure\nInstructions"}]})
    answer = client.post("/brains/suggestions/review", json=payload)
    assert answer.status_code == 200, answer.text
    assert "not-for-the-model" not in agent.interprets[0] and "private-brain-key" not in agent.interprets[0]
    assert "Durable private instructions" in agent.interprets[0]
    suggestion = answer.json()[0]["id"]
    assert [s["id"] for s in client.get("/brains/suggestions").json()] == [suggestion]
    assert client.post(f"/brains/suggestions/{suggestion}/dismiss", json={}).status_code == 200
    assert client.get("/brains/suggestions").json() == []
    agent.summary = '{"suggestions":[{"note_id":"foreign"}]}'
    assert client.post("/brains/suggestions/review", json=payload).status_code == 502
    assert [r["kind"] for r in client.get("/usage/records").json()] == ["brain_suggestions"] * 2  # both calls counted


def test_review_agent_failure_is_a_503(client, armory, agent):
    armory_ok(armory)
    client.put(PERSONAL, json=SAVE)
    note = make_note(client)
    agent.fail = "down"
    body = {"note_ids": [note["id"]], "explicit_private": [note["id"]]}
    answer = client.post("/brains/suggestions/review", json=body)
    assert answer.status_code == 503 and "Manual promotion remains available" in answer.json()["detail"]


def test_dismiss_of_another_accounts_suggestion_is_404(client, db_gateway):
    db_gateway.records[("brain_suggestions", "s1")] = {"id": "s1", "owner": "someone-else", "status": "suggested"}
    assert client.post("/brains/suggestions/s1/dismiss", json={}).status_code == 404


def test_promote_review_and_reconcile(client, armory):
    armory_ok(armory)
    destination = client.put(PERSONAL, json=SAVE).json()
    note = make_note(client)
    review = client.get(f"/brains/notes/{note['id']}/review").json()
    store = {}

    def vault(request):
        sent = json.loads(request.content)
        if sent["operation"] == "read":
            return httpx.Response(200, json={"content": store[sent["path"]]}) if sent["path"] in store else httpx.Response(404, json={})
        store[sent["path"]] = sent["text"]
        return httpx.Response(200, json={"success": True})

    armory.handler = vault
    body = {"source_hash": review["source_hash"], "source_revision": review["source_revision"], "scope": "personal",
            "destination_revision": destination["revision"], "generation": destination["generation"],
            "path": "Inbox/Procedure.md", "draft": "# Procedure", "idempotency_key": "k1"}
    done = client.post(f"/brains/notes/{note['id']}/promote", json=body)
    assert done.status_code == 200 and done.json()["status"] == "published"
    assert store == {"Inbox/Procedure.md": "# Procedure"}
    assert [p["status"] for p in client.get("/brains/promotions").json()] == ["published"]
    assert client.post(f"/brains/promotions/{done.json()['id']}/reconcile").status_code == 200
    assert client.post("/brains/promotions/nope/reconcile").status_code == 404
    assert client.get("/brains/notes/" + "0" * 32 + "/review").status_code == 404


def test_purge_removes_the_accounts_records_and_retires_armory_state(client, armory, db_gateway):
    armory_ok(armory)
    client.put(PERSONAL, json=SAVE)
    other = {"id": "x", "owner": "u-2"}
    db_gateway.records[("brain_suggestions", "x")] = other
    assert client.delete("/brains/accounts/u-1").status_code == 204
    assert client.get(PERSONAL).json()["revision"] == 0
    assert db_gateway.records[("brain_suggestions", "x")] == other
    armory.handler = lambda request: httpx.Response(503)
    assert client.delete("/brains/accounts/u-1").status_code == 502
