"""/api/brains passes on to Stronghold's /brains routes after the login (and chat.use) check."""

import json

import httpx

from tests.test_admin import login, make_member
from tests.test_registration import as_admin

ROUTES = [
    ("GET", "/api/brains/connections/personal", "/brains/connections/personal"),
    ("PUT", "/api/brains/connections/instance", "/brains/connections/instance"),
    ("POST", "/api/brains/connections/personal/test", "/brains/connections/personal/test"),
    ("GET", "/api/brains/destinations", "/brains/destinations"),
    ("POST", "/api/brains/browse", "/brains/browse"),
    ("GET", "/api/brains/promotions", "/brains/promotions"),
    ("GET", "/api/brains/notes/abc/review", "/brains/notes/abc/review"),
    ("POST", "/api/brains/notes/abc/promote", "/brains/notes/abc/promote"),
    ("POST", "/api/brains/promotions/p1/reconcile", "/brains/promotions/p1/reconcile"),
    ("POST", "/api/brains/suggestions/review", "/brains/suggestions/review"),
    ("GET", "/api/brains/suggestions", "/brains/suggestions"),
    ("POST", "/api/brains/suggestions/s1/dismiss", "/brains/suggestions/s1/dismiss"),
]


def test_every_route_needs_a_login(client):
    for method, url, _ in ROUTES:
        assert client.request(method, url, json={}).status_code == 401, url


def test_every_route_goes_to_its_stronghold_path_with_body_and_status(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(207, json={"path": request.url.path, "body": json.loads(request.content or b"null")})
    for method, url, path in ROUTES:
        answer = client.request(method, url, json={"label": "x"})
        assert answer.status_code == 207, url
        assert answer.json() == {"path": path, "body": {"label": "x"}}


def test_stronghold_refusals_pass_through_unchanged(client, upstream):
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(412, json={"detail": "A destination changed during review. Review again."})
    answer = client.post("/api/brains/suggestions/review", json={})
    assert answer.status_code == 412 and answer.json()["detail"].startswith("A destination changed")


def test_stronghold_down_is_a_502(client, upstream):
    as_admin(client)
    upstream.unreachable = True
    assert client.get("/api/brains/connections/personal").status_code == 502


def test_member_needs_chat_use_for_notes_and_suggestions(client, email, upstream):
    make_member(client, email, "alice")
    login(client, "alice")
    upstream.handler = lambda request: httpx.Response(200, json=[])
    assert client.get("/api/brains/destinations").status_code == 200
    assert client.get("/api/brains/promotions").status_code == 200  # members hold chat.use


def test_the_old_internal_resolve_route_is_gone(client):
    assert client.post("/api/brains/internal/resolve", json={"scope": "instance", "operation": "read"}).status_code in (404, 405)
