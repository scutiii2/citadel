import json

import httpx
import pytest

from tests.test_registration import as_admin

FID = "a" * 32


def test_speak_and_voices_require_login(client, upstream):
    assert client.post("/api/bard/speak", json={"text": "hi", "voice": "v2"}).status_code == 401
    assert client.get("/api/bard/voices").status_code == 401
    assert not upstream.requests


def test_speak_and_installed_voices_are_proxied(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"voices": ["v2"]} if r.method == "GET" else {"file_id": FID, "duration_s": 1.5, "voice": "v2"})
    assert client.get("/api/bard/voices").json() == {"voices": ["v2"]}
    assert upstream.requests[-1].url.path == "/api/voices"
    response = client.post("/api/bard/speak", json={"text": "hello", "voice": "v2"})
    assert response.status_code == 200
    assert response.json() == {"file_id": FID, "duration_s": 1.5, "voice": "v2"}
    sent = upstream.requests[-1]
    assert sent.url.path == "/api/speak" and json.loads(sent.content) == {"text": "hello", "voice": "v2"}
    assert sent.headers["x-requester-username"]
    actor = client.get("/api/auth/me").json()["id"]
    logs = client.get("/api/logs/action", params={"actor": actor}).json()
    speech_log = next(row for row in logs if row["source"] == "bard.speak")
    assert "hello" not in speech_log["message"] and FID in speech_log["message"]


@pytest.mark.parametrize("code, expected", [(400, 400), (413, 413), (401, 502), (503, 502)])
def test_speak_maps_bard_failures(client, upstream, code, expected):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(code, json={"message": "Unable to speak"})
    assert client.post("/api/bard/speak", json={"text": "hi", "voice": "v2"}).status_code == expected


def test_speak_rejects_empty_or_invalid_input(client, upstream):
    as_admin(client)
    for payload in [{}, {"text": ""}, {"text": "hi", "voice": ""}, {"text": 123}]:
        assert client.post("/api/bard/speak", json=payload).status_code == 422
    assert not upstream.requests


def test_speech_json_outage_is_502(client, upstream):
    as_admin(client)

    def down(request):
        raise httpx.ConnectError("down")

    upstream.handler = down
    assert client.get("/api/bard/voices").status_code == 502
    assert client.post("/api/bard/speak", json={"text": "hi", "voice": "v1"}).status_code == 502


def test_audio_requires_login(client, upstream):
    assert client.get(f"/api/bard/audio/{FID}").status_code == 401
    assert not upstream.requests


def test_audio_streams_from_bard_with_identity_and_range(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(
        206, content=b"2345",
        headers={"content-type": "audio/mpeg", "content-range": "bytes 2-5/10", "accept-ranges": "bytes"},
    )
    response = client.get(f"/api/bard/audio/{FID}", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == b"2345"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["cache-control"] == "no-store"
    sent = upstream.requests[-1]
    assert sent.url.path == f"/api/files/{FID}"
    assert sent.headers["range"] == "bytes=2-5"
    assert sent.headers["x-requester-username"]


def test_missing_or_expired_audio_is_404(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(404, json={"error": "file_not_found"})
    assert client.get(f"/api/bard/audio/{FID}").status_code == 404


def test_bard_rejecting_the_token_is_not_shown_as_a_browser_auth_error(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(401, json={"error": "Invalid or missing internal API token"})
    assert client.get(f"/api/bard/audio/{FID}").status_code == 502


def test_unreachable_bard_is_502(client, upstream):
    as_admin(client)

    def down(request):
        raise httpx.ConnectError("down")

    upstream.handler = down
    assert client.get(f"/api/bard/audio/{FID}").status_code == 502


def test_a_malformed_id_is_rejected_before_bard_is_called(client, upstream):
    as_admin(client)
    assert client.get("/api/bard/audio/not-hex").status_code == 422
    assert not upstream.requests
