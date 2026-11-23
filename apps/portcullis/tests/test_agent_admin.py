"""/api/admin/agents: forwarded to ai_agent's /agents routes, agents.manage only."""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

import json

import httpx

from tests.conftest import FakeEmailSender, FakeUpstream
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

CONFIG = {"role": "specialist", "label": "Calc", "port": 9103, "llm": {"provider": "anthropic", "gateway": "claude"}}


def ai_agent(request: httpx.Request) -> httpx.Response:
    path, method = request.url.path, request.method
    if path == "/agents/gateways":
        return httpx.Response(200, json={"providers": {"anthropic": [{"id": "claude", "label": "Claude"}]}})
    if path == "/agents/files" and method == "GET":
        return httpx.Response(200, json={"agents": [{"id": "ember", "port": 9100}]})
    if path == "/agents/files" and method == "POST":
        body = json.loads(request.content)
        for key in ("orchestrator", "internal_role"):
            if key in body["config"]:
                return httpx.Response(400, json={"error": f"calc.json: {key} is not a known field"})
        if body["id"] == "ember":
            return httpx.Response(409, json={"error": "agent 'ember' already exists"})
        return httpx.Response(201, json={"id": body["id"], **body["config"]})
    if path == "/agents/files/calc" and method == "PUT":
        return httpx.Response(200, json={"id": "calc", **json.loads(request.content)})
    if path == "/agents/files/ember" and method == "DELETE":
        return httpx.Response(409, json={"error": "'ember' is the entry agent"})
    if path == "/agents/files/calc/reset" and method == "POST":
        return httpx.Response(200, json={"id": "calc", **CONFIG, "overridden": False})
    if path == "/agents/files/ember/reset" and method == "POST":
        return httpx.Response(409, json={"error": "agent 'ember' already uses its default"})
    if path == "/agents/files/calc" and method == "DELETE":
        return httpx.Response(200, json={"deleted": "calc"})
    if path == "/agents/prompts" and method == "GET":
        return httpx.Response(200, json={"values": {"app_name": "Ember"}, "defaults": {"app_name": "Ember"}, "overridden": []})
    if path == "/agents/prompts" and method == "PUT":
        changes = json.loads(request.content)
        if "bogus" in changes:
            return httpx.Response(400, json={"error": "unknown prompt 'bogus'"})
        return httpx.Response(200, json={"values": changes, "defaults": {}, "overridden": sorted(changes)})
    if path == "/agents/prompt-preview":
        return httpx.Response(200, json={"prompt": "PROMPT for " + json.loads(request.content)["id"]})
    return httpx.Response(404, json={"error": "no route"})


def test_admin_lists_creates_updates_and_deletes(client, upstream: FakeUpstream) -> None:
    upstream.handler = ai_agent
    as_admin(client)

    assert client.get("/api/admin/agents/gateways").json()["providers"]["anthropic"][0]["id"] == "claude"
    assert client.get("/api/admin/agents").json() == {"agents": [{"id": "ember", "port": 9100}]}

    created = client.post("/api/admin/agents", json={"id": "calc", "config": CONFIG})
    assert (created.status_code, created.json()["port"]) == (201, 9103)
    sent = upstream.requests[-1]
    assert str(sent.url) == "http://agent-a.internal/agents/files"
    assert requester(sent)["username"] == "root"
    assert len(requester(sent)["sub"]) == 32

    assert client.put("/api/admin/agents/calc", json={"config": CONFIG}).json()["id"] == "calc"
    assert json.loads(upstream.requests[-1].content) == CONFIG
    reset = client.post("/api/admin/agents/calc/reset", json={})
    assert (reset.status_code, reset.json()["overridden"]) == (200, False)
    assert str(upstream.requests[-1].url) == "http://agent-a.internal/agents/files/calc/reset"
    assert client.delete("/api/admin/agents/calc").status_code == 204


def test_ai_agent_refusals_pass_through(client, upstream: FakeUpstream) -> None:
    upstream.handler = ai_agent
    as_admin(client)

    clash = client.post("/api/admin/agents", json={"id": "ember", "config": CONFIG})
    assert (clash.status_code, clash.json()["detail"]) == (409, "agent 'ember' already exists")
    assert client.delete("/api/admin/agents/ember").status_code == 409
    assert client.post("/api/admin/agents/ember/reset", json={}).status_code == 409
    assert client.put("/api/admin/agents/ghost", json={"config": CONFIG}).status_code == 404


def test_bad_ids_and_bodies_are_rejected_before_ai_agent(client, upstream: FakeUpstream) -> None:
    upstream.handler = ai_agent
    as_admin(client)
    before = len(upstream.requests)

    assert client.post("/api/admin/agents", json={"id": "Bad Id", "config": CONFIG}).status_code == 422
    assert client.post("/api/admin/agents", json={"id": "calc"}).status_code == 422
    assert client.delete("/api/admin/agents/Bad_Id").status_code == 422
    assert len(upstream.requests) == before


def test_unreachable_ai_agent_is_502(client, upstream: FakeUpstream) -> None:
    upstream.unreachable = True
    as_admin(client)
    assert client.get("/api/admin/agents").status_code == 502


def test_needs_login_and_agents_manage(client_factory, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = ai_agent
    anonymous = client_factory()
    assert anonymous.get("/api/admin/agents").status_code == 401

    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.get("/api/admin/agents").status_code == 403
    assert member.post("/api/admin/agents", json={"id": "calc", "config": CONFIG}).status_code == 403
    assert member.delete("/api/admin/agents/calc").status_code == 403
    assert upstream.requests == []


def test_shared_prompts_read_change_log_and_preview(client, upstream: FakeUpstream) -> None:
    upstream.handler = ai_agent
    as_admin(client)

    assert client.get("/api/admin/agent-prompts").json()["values"] == {"app_name": "Ember"}
    changed = client.put("/api/admin/agent-prompts", json={"app_name": "Ascended", "roster_intro": None})
    assert (changed.status_code, changed.json()["overridden"]) == (200, ["app_name", "roster_intro"])
    assert json.loads(upstream.requests[-1].content) == {"app_name": "Ascended", "roster_intro": None}
    assert client.put("/api/admin/agent-prompts", json={"bogus": "x"}).status_code == 400
    assert client.put("/api/admin/agent-prompts", json={"app_name": 5}).status_code == 422

    preview = client.post("/api/admin/agent-prompt-preview", json={"id": "calc", "config": CONFIG, "caveman": True})
    assert preview.json() == {"prompt": "PROMPT for calc"}
    assert json.loads(upstream.requests[-1].content) == {"id": "calc", "config": CONFIG, "caveman": True}
    assert client.post("/api/admin/agent-prompt-preview", json={"id": "Bad Id", "config": CONFIG}).status_code == 422


def test_shared_prompts_need_agents_manage(client_factory, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = ai_agent
    assert client_factory().get("/api/admin/agent-prompts").status_code == 401
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.get("/api/admin/agent-prompts").status_code == 403
    assert member.put("/api/admin/agent-prompts", json={"app_name": "x"}).status_code == 403
    assert member.post("/api/admin/agent-prompt-preview", json={"id": "calc", "config": CONFIG}).status_code == 403
    assert upstream.requests == []


def test_role_config_is_forwarded_and_retired_key_refusal_is_preserved(client, upstream):
    upstream.handler = ai_agent
    as_admin(client)
    response = client.post("/api/admin/agents", json={"id": "calc", "config": CONFIG})
    assert response.status_code == 201 and response.json()["role"] == "specialist"
    assert json.loads(upstream.requests[-1].content)["config"] == CONFIG
    response = client.post("/api/admin/agents", json={"id": "calc", "config": {**CONFIG, "orchestrator": True}})
    assert response.status_code == 400
    assert "orchestrator is not a known field" in response.json()["detail"]


def servers_agent(stored: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.startswith("/agents/servers"):
            return ai_agent(request)
        if request.method == "GET":
            return httpx.Response(200, json={"servers": stored})
        server_id = request.url.path.rsplit("/", 1)[1]
        if request.method == "DELETE":
            stored.pop(server_id, None)
            return httpx.Response(200, json={"deleted": server_id, "applies": "next start"})
        body = json.loads(request.content)
        if body.get("transport") == "http" and not body.get("url"):
            return httpx.Response(400, json={"error": "transport 'http' requires 'url'"})
        stored[server_id] = body
        return httpx.Response(200, json={"saved": server_id, "applies": "next start"})
    return handler


def test_servers_list_add_and_remove_never_show_a_header_value(client, upstream: FakeUpstream) -> None:
    stored = {"main": {"label": "armory", "transport": "http", "url": "http://armory:29600/mcp",
                       "auth": {"type": "header", "header_name": "X-Token", "header_value": "s3cret"}}}
    upstream.handler = servers_agent(stored)
    as_admin(client)

    listed = client.get("/api/admin/servers")
    assert "s3cret" not in listed.text
    assert listed.json()["servers"]["main"]["auth"] == {"type": "header", "header_name": "X-Token", "has_value": True}

    # editing without retyping the secret keeps the stored one
    edit = {"label": "armory", "transport": "http", "url": "http://armory:29600/mcp2",
            "auth": {"type": "header", "header_name": "X-Token"}}
    assert client.put("/api/admin/servers/main", json=edit).status_code == 200
    assert stored["main"]["url"].endswith("/mcp2") and stored["main"]["auth"]["header_value"] == "s3cret"

    assert client.put("/api/admin/servers/docs", json={"label": "docs", "transport": "http"}).json()["detail"] == (
        "transport 'http' requires 'url'")
    invalid_token = "private-header-" * 200
    refused = client.put("/api/admin/servers/main", json={
        **edit, "auth": {**edit["auth"], "header_value": invalid_token}})
    assert refused.status_code == 422
    assert invalid_token not in refused.text

    assert client.put("/api/admin/servers/Bad Id", json=edit).status_code == 422
    assert client.put("/api/admin/servers/x", json={**edit, "extra": 1}).status_code == 422
    assert client.delete("/api/admin/servers/main").json() == {"deleted": "main"}
    assert stored == {}


def test_servers_need_agents_manage(client_factory, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = servers_agent({})
    assert client_factory().get("/api/admin/servers").status_code == 401
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.get("/api/admin/servers").status_code == 403
    assert member.delete("/api/admin/servers/main").status_code == 403
    assert upstream.requests == []


def test_model_name_routes_are_removed(client) -> None:
    admin = as_admin(client)
    assert admin.get("/api/admin/model-names").status_code == 404


def test_treasury_address_routes_are_removed(client):
    admin = as_admin(client)
    assert admin.get("/api/admin/treasury-address").status_code == 404
    assert admin.put("/api/admin/treasury-address", json={"url": "http://treasury:29602"}).status_code == 404


def test_origin_overrides_are_hidden_and_addresses_pass_through(client, upstream: FakeUpstream) -> None:
    stored = {"bard": {"label": "Bard", "transport": "http", "service_id": "s", "path": "/mcp",
                       "auth": {"type": "header", "header_name": "X-Token", "header_value": "parent"},
                       "origins": [{"origin_id": "o1", "origin": "http://bard:29400"},
                                   {"origin_id": "o2", "origin": None, "header_value": "second"}]}}
    sent = {}

    def handler(request):
        if request.url.path == "/agents/servers/lookup":
            sent["lookup"] = json.loads(request.content)
            return httpx.Response(200, json={"found": False, "origin": "http://x:1", "path": "", "origin_id": None, "group": None})
        if request.method == "PUT":
            sent["put"] = json.loads(request.content)
            return httpx.Response(200, json={"saved": "bard", "applies": "next start"})
        return servers_agent(stored)(request)

    upstream.handler = handler
    as_admin(client)
    listed = client.get("/api/admin/servers")
    assert "second" not in listed.text and "parent" not in listed.text
    origins = listed.json()["servers"]["bard"]["origins"]
    assert origins[0] == {"origin_id": "o1", "origin": "http://bard:29400", "has_override": False}
    assert origins[1] == {"origin_id": "o2", "origin": None, "has_override": True}

    body = {"label": "Bard", "transport": "http", "path": "/mcp",
            "auth": {"type": "header", "header_name": "X-Token"},
            "addresses": [{"address": "http://bard:29400/mcp", "name": "bard", "header_value": "x"}]}
    assert client.put("/api/admin/servers/bard", json=body).status_code == 200
    assert sent["put"]["addresses"][0]["address"] == "http://bard:29400/mcp"
    assert sent["put"]["auth"]["header_value"] == "parent"          # the parent token is kept when not retyped
    assert client.post("/api/admin/servers/lookup", json={"address": "http://x:1"}).json()["found"] is False
    assert sent["lookup"] == {"address": "http://x:1"}
    assert client.post("/api/admin/servers/lookup", json={"address": "x", "extra": 1}).status_code == 422


def test_lookup_needs_agents_manage(client_factory, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = servers_agent({})
    assert client_factory().post("/api/admin/servers/lookup", json={"address": "http://x:1"}).status_code == 401
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.post("/api/admin/servers/lookup", json={"address": "http://x:1"}).status_code == 403
    assert upstream.requests == []


def test_catalog_save_preserves_legions_treasury_outage_message(client, upstream: FakeUpstream) -> None:
    message = "[1002] Treasury is unavailable. Nothing was saved."

    def handler(request):
        if request.method == "PUT" and request.url.path == "/agents/servers/bard":
            assert request.extensions["timeout"]["read"] > 220
            return httpx.Response(502, json={"error": message})
        return servers_agent({})(request)

    upstream.handler = handler
    as_admin(client)
    response = client.put("/api/admin/servers/bard", json={
        "label": "Bard", "transport": "http",
        "addresses": [{"address": "http://bard:29400/mcp", "name": "bard"}],
    })
    assert response.status_code == 502
    assert response.json()["detail"] == message


def test_connection_tests_reach_legion_and_need_agents_manage(client_factory, client, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    upstream.handler = lambda request: (httpx.Response(200, json={"ok": True, "message": request.url.path})
                                        if request.url.path.endswith("/test") else ai_agent(request))
    as_admin(client)
    assert client.post("/api/admin/model-gateways/decision/laya/test", json={}).json()["message"] == "/agents/model-gateways/decision/laya/test"
    assert client.post("/api/admin/servers/docs/test", json={}).json()["message"] == "/agents/servers/docs/test"
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.post("/api/admin/model-gateways/conversation/claude/test", json={}).status_code == 403


def test_model_gateways_pass_through_to_legion_and_need_agents_manage(client_factory, client, email: FakeEmailSender, upstream: FakeUpstream) -> None:
    seen = []

    def legion(request):
        seen.append((request.method, request.url.path))
        if request.url.path.startswith("/agents/model-gateways/"):
            return httpx.Response(200, json={"gateways": []} if request.method == "GET" else {"ok": True})
        return ai_agent(request)

    upstream.handler = legion
    as_admin(client)
    assert client.get("/api/admin/model-gateways/conversation").json() == {"gateways": []}
    assert client.put("/api/admin/model-gateways/decision/laya", json={"kind": "scuti"}).status_code == 200
    assert client.delete("/api/admin/model-gateways/decision/laya").status_code == 200
    assert client.get("/api/admin/model-gateways/conversation/claude/models").status_code == 200
    assert client.get("/api/admin/model-gateways/other").status_code == 422
    assert client.put("/api/admin/model-gateways/decision/Bad Id", json={}).status_code == 422
    assert ("PUT", "/agents/model-gateways/decision/laya") in seen and ("DELETE", "/agents/model-gateways/decision/laya") in seen
    member = client_factory()
    make_member(member, email)
    login(member, "alice")
    assert member.get("/api/admin/model-gateways/conversation").status_code == 403
    assert member.put("/api/admin/model-gateways/decision/laya", json={}).status_code == 403
