"""/api/attachments and /api/bard/speak|voices: Portcullis checks the login and permission, Stronghold does the rest."""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeUpstream
from tests.test_permission_split import limited_account
from tests.test_registration import as_admin

ROUTES = [("text", "a.txt"), ("table", "a.csv"), ("pdf", "a.pdf"), ("audio", "a.mp3"), ("document", "a.pdf"),
          ("dictate", "a.webm"), ("dictate/partial", "a.webm"), ("file", "a.txt")]


def body(name: str = "a.txt", data: bytes = b"abc") -> dict:
    return {"filename": name, "data": base64.b64encode(data).decode()}


@pytest.mark.parametrize("path, name", ROUTES)
def test_a_login_is_needed(client: TestClient, upstream: FakeUpstream, path: str, name: str) -> None:
    assert client.post(f"/api/attachments/{path}", json=body(name)).status_code == 401
    assert not upstream.requests


@pytest.mark.parametrize("path, name", ROUTES)
def test_upload_permission_is_needed(client: TestClient, email: str, upstream: FakeUpstream, path: str, name: str) -> None:
    limited_account(client, email, "chat.use")
    upstream.requests.clear()

    assert client.post(f"/api/attachments/{path}", json=body(name)).status_code == 403
    assert not upstream.requests


@pytest.mark.parametrize("path, name", ROUTES)
def test_the_request_goes_to_stronghold_with_the_identity(client: TestClient, upstream: FakeUpstream, path: str, name: str) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"ok": True})
    upstream.requests.clear()

    response = client.post(f"/api/attachments/{path}", json=body(name, b"hello"))

    assert response.status_code == 200 and response.json() == {"ok": True}
    sent = upstream.requests[-1]
    assert sent.method == "POST" and sent.url.path == f"/attachments/{path}"
    assert json.loads(sent.content) == body(name, b"hello")
    assert requester(sent)["username"] == "root" and requester(sent)["sub"]
    assert "cookie" not in sent.headers


@pytest.mark.parametrize("code", [400, 413, 422])
def test_stronghold_refusals_reach_the_browser_unchanged(client: TestClient, upstream: FakeUpstream, code: int) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(code, json={"detail": "Can't read '.mp4' files"})

    response = client.post("/api/attachments/text", json=body("movie.mp4"))

    assert response.status_code == code and response.json() == {"detail": "Can't read '.mp4' files"}


def test_a_stronghold_outage_is_a_502(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(503, json={"detail": "down"})
    assert client.post("/api/attachments/text", json=body()).status_code == 502

    upstream.unreachable = True
    assert client.post("/api/attachments/audio", json=body("a.mp3")).status_code == 502


def test_a_big_body_is_not_cut_off_on_the_way(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={})

    response = client.post("/api/attachments/text", json=body("a.txt", b"x" * (3 * 1024 * 1024)))

    assert response.status_code == 200
    assert len(json.loads(upstream.requests[-1].content)["data"]) == 4 * 1024 * 1024


# --- bard speak and voices ------------------------------------------------------------------


def test_a_20_mb_upload_is_passed_on_with_a_long_timeout(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"ok": True})

    response = client.post("/api/attachments/file", json=body("a.mp3", b"x" * (20 * 1024 * 1024)))

    assert response.status_code == 200
    assert upstream.requests[-1].extensions["timeout"]["read"] == 150.0


def test_an_upload_keeps_the_reason_storage_failed(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(502, json={"detail": "File storage is unavailable"})

    response = client.post("/api/attachments/file", json=body("a.png"))

    assert response.status_code == 502 and response.json() == {"detail": "File storage is unavailable"}


def test_speech_needs_a_login(client: TestClient, upstream: FakeUpstream) -> None:
    assert client.post("/api/bard/speak", json={"text": "hi", "voice": "v2"}).status_code == 401
    assert client.get("/api/bard/voices").status_code == 401
    assert not upstream.requests


def test_speak_and_voices_are_passed_to_stronghold(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"voices": ["v2"]} if r.method == "GET" else {"file_id": "a" * 32})
    upstream.requests.clear()

    assert client.get("/api/bard/voices").json() == {"voices": ["v2"]}
    assert client.post("/api/bard/speak", json={"text": "hello", "voice": "v2"}).json() == {"file_id": "a" * 32}

    voices, speak = upstream.requests
    assert (voices.method, voices.url.path) == ("GET", "/bard/voices")
    assert (speak.method, speak.url.path) == ("POST", "/bard/speak")
    assert json.loads(speak.content) == {"text": "hello", "voice": "v2"}
    assert requester(speak)["username"] == "root"


@pytest.mark.parametrize("code, expected", [(400, 400), (413, 413), (422, 422), (503, 502)])
def test_speak_keeps_stronghold_refusals_and_maps_outages(client: TestClient, upstream: FakeUpstream, code: int, expected: int) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(code, json={"detail": "Unable to speak"})

    assert client.post("/api/bard/speak", json={"text": "hi", "voice": "v2"}).status_code == expected
