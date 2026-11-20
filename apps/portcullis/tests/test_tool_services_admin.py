"""Stronghold tool service administration and status through Portcullis."""

import json

import httpx
import pytest

from tests.auth_helpers import assertion, requester
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

ADMIN = "/api/admin/tool-services"
STATUS = "/tool-services/status"
FALLBACK = "Check Stronghold Admin, Tool services."
ACTIONS = [
    ("GET", "", None),
    ("POST", "/lookup", {"address": "http://bard.test:29400"}),
    ("PUT", "/bard", {"enabled": True, "addresses": [{"address": "http://bard.test:29400"}]}),
    ("DELETE", "/bard", None),
    ("POST", "/bard/test", {}),
]


@pytest.mark.parametrize("method, suffix, body", ACTIONS)
def test_admin_request_reaches_stronghold(client, upstream, method, suffix, body):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"forwarded": True})
    response = client.request(method, ADMIN + suffix, json=body)
    assert response.status_code == 200
    assert response.json() == {"forwarded": True}
    sent = upstream.requests[-1]
    assert (sent.method, sent.url.path) == (method, "/admin/tool-services" + suffix)
    assert (json.loads(sent.content) if sent.content else None) == body
    assert assertion(sent, "stronghold")["iss"] == "portcullis"
    assert requester(sent)["username"] == "root"


def test_admin_requests_need_extensions_manage(client, email, upstream):
    make_member(client, email)
    login(client, "alice")
    upstream.requests.clear()
    for method, suffix, body in ACTIONS:
        assert client.request(method, ADMIN + suffix, json=body).status_code == 403
    assert not upstream.requests


def test_treasury_unavailable_refusal_reaches_admin(client, upstream):
    as_admin(client)
    detail = "[1002] Treasury is unavailable. Nothing was saved."
    upstream.handler = lambda _: httpx.Response(502, json={"detail": detail})
    response = client.put(ADMIN + "/bard", json=ACTIONS[2][2])
    assert (response.status_code, response.json()["detail"]) == (502, detail)


@pytest.mark.parametrize("reason", [
    "Bard is disabled in Stronghold Admin.",
    "Configure Bard in Stronghold Admin.",
    "Set the Bard token in Stronghold Admin.",
])
def test_connection_status_allows_only_each_services_own_reasons(client, upstream, reason):
    as_admin(client)

    def respond(request):
        assert request.url.path == STATUS
        return httpx.Response(200, json={
            "bard": {"ready": False, "reason": reason},
            "scribe": {"ready": True, "reason": "ignored"},
            "reader": {"ready": False, "reason": reason},
        })

    upstream.handler = respond
    assert client.get("/api/connection-status").json() == {
        "bard": {"ready": False, "reason": reason},
        "scribe": {"ready": True, "reason": None},
        "reader": {"ready": False, "reason": FALLBACK},
    }


def test_an_outage_is_not_ready_and_lists_three_config_issues(client, upstream):
    as_admin(client)
    upstream.unreachable = True
    assert client.get("/api/connection-status").json() == {
        name: {"ready": False, "reason": FALLBACK}
        for name in ("bard", "scribe", "reader")
    }
    response = client.get("/api/config-issues")
    assert response.status_code == 200
    assert {(issue["key"], issue["message"]) for issue in response.json()
            if issue["file"] == "Stronghold Tool services"} == {
        (name, FALLBACK) for name in ("bard", "scribe", "reader")
    }
