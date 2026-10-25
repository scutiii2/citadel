# apps/Ember/ember_api/tests/test_admin_tuning.py
"""/api/admin/tuning: forwarded to garrison's /agents/tuning, tuning.manage only."""

from __future__ import annotations

import json

import httpx

from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

VIEW = {"defaults": {"token_limits": {"default": {"max_tool_rounds": 15}}}, "overrides": {}, "effective": {"token_limits": {"default": {"max_tool_rounds": 15}}}}


def garrison(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/agents/tuning" and request.method == "GET":
        return httpx.Response(200, json=VIEW)
    if request.url.path == "/agents/tuning" and request.method == "PUT":
        changes = json.loads(request.content)
        if "bad" in changes:
            return httpx.Response(400, json={"error": "'bad' cannot be edited here"})
        return httpx.Response(200, json={**VIEW, "overrides": changes})
    return httpx.Response(404, json={"error": "no route"})


def test_admin_reads_and_edits(client, upstream: FakeUpstream) -> None:
    upstream.handler = garrison
    as_admin(client)

    assert client.get("/api/admin/tuning").json() == VIEW
    saved = client.put("/api/admin/tuning", json={"changes": {"token_limits.default.max_tool_rounds": 20}})
    assert saved.status_code == 200
    assert saved.json()["overrides"] == {"token_limits.default.max_tool_rounds": 20}
    sent = upstream.requests[-1]
    assert sent.headers["x-requester-username"] == "root"
    assert json.loads(sent.content) == {"token_limits.default.max_tool_rounds": 20}


def test_garrison_refusal_is_a_400_with_its_message(client, upstream: FakeUpstream) -> None:
    upstream.handler = garrison
    as_admin(client)
    refused = client.put("/api/admin/tuning", json={"changes": {"bad": 1}})
    assert (refused.status_code, refused.json()["detail"]) == (400, "'bad' cannot be edited here")


def test_garrison_down_is_a_502(client, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: httpx.Response(503, json={"error": "down"})
    as_admin(client)
    assert client.get("/api/admin/tuning").status_code == 502


def test_a_change_is_written_to_the_activity_log(client, upstream: FakeUpstream) -> None:
    upstream.handler = garrison
    as_admin(client)
    client.put("/api/admin/tuning", json={"changes": {"token_limits.default.max_tool_rounds": 20}})
    entries = client.get("/api/logs/action", params={"actor": str(client.get("/api/auth/me").json()["id"])}).json()
    entry = next(e for e in entries if e["source"] == "tuning.update")
    details = json.loads(entry["details"])
    assert details["before"] == VIEW
    assert details["after"]["overrides"] == {"token_limits.default.max_tool_rounds": 20}


def test_a_member_without_the_permission_is_refused(client, upstream: FakeUpstream, email: FakeEmailSender) -> None:
    upstream.handler = garrison
    make_member(client, email)
    login(client, "alice")
    assert client.get("/api/admin/tuning").status_code == 403
    assert client.put("/api/admin/tuning", json={"changes": {}}).status_code == 403
