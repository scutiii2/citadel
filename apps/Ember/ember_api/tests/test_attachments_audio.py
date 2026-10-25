import base64

import httpx
import pytest

from tests.test_registration import as_admin


def body(name="a.mp3", data=b"abc"):
    return {"filename": name, "data": base64.b64encode(data).decode()}


def test_audio_requires_login(client, upstream):
    assert client.post("/api/attachments/audio", json=body()).status_code == 401
    assert not upstream.requests


def test_audio_is_forwarded_with_identity(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(
        200, json={"file_id": "a" * 32, "duration_s": 3.2, "size_bytes": 3, "expires_at": 99.0}
    )
    response = client.post("/api/attachments/audio", json=body("..\\x\\talk.m4a", b"abc"))
    assert response.status_code == 200
    assert response.json() == {"filename": "talk.m4a", "file_id": "a" * 32, "duration_s": 3.2, "expires_at": 99.0}
    sent = upstream.requests[-1]
    assert sent.url.path == "/api/files" and sent.content == b"abc"
    assert sent.headers["x-requester-username"] and sent.headers["x-filename"] == "talk.m4a"


def test_unsupported_suffix_is_400_without_calling_scribe(client, upstream):
    as_admin(client)
    assert client.post("/api/attachments/audio", json=body("a.exe")).status_code == 400
    assert not upstream.requests


def test_bad_base64_is_400(client, upstream):
    as_admin(client)
    assert client.post("/api/attachments/audio", json={"filename": "a.mp3", "data": "!!!"}).status_code == 400


def test_scribe_rejecting_audio_is_400_with_its_message(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(400, json={"error": "audio_rejected", "message": "Not audio."})
    response = client.post("/api/attachments/audio", json=body())
    assert response.status_code == 400 and "Not audio." in response.text


def test_scribe_token_refusal_and_outage_are_502(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(401, json={"error": "Invalid or missing internal API token"})
    assert client.post("/api/attachments/audio", json=body()).status_code == 502


def test_dictate_forwards_audio_and_returns_transcript(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"text": "hello", "duration_s": 2.5})
    response = client.post("/api/attachments/dictate", json=body("../speech.webm"))
    assert response.status_code == 200
    assert response.json() == {"text": "hello", "duration_s": 2.5}
    sent = upstream.requests[-1]
    assert sent.url.path == "/api/transcribe" and sent.content == b"abc"
    assert sent.headers["x-requester-username"] and sent.headers["x-filename"] == "speech.webm"
    actor = client.get("/api/auth/me").json()["id"]
    logs = client.get("/api/logs/action", params={"actor": actor}).json()
    entry = next(row for row in logs if row["source"] == "attachments.dictate")
    assert "hello" not in entry["message"] and "3 bytes" in entry["message"]


def test_dictate_requires_login(client, upstream):
    assert client.post("/api/attachments/dictate", json=body()).status_code == 401
    assert not upstream.requests


def test_dictate_rejects_decoded_audio_over_20_mb(client, upstream):
    as_admin(client)
    response = client.post("/api/attachments/dictate", json=body("a.webm", b"x" * (20 * 1024 * 1024 + 1)))
    assert response.status_code == 413
    assert not upstream.requests


@pytest.mark.parametrize("payload", [body("a.exe"), {"filename": "a.webm", "data": "!!!"}])
def test_dictate_validates_before_upstream(client, upstream, payload):
    as_admin(client)
    assert client.post("/api/attachments/dictate", json=payload).status_code == 400
    assert not upstream.requests


@pytest.mark.parametrize("code, expected", [(400, 400), (413, 413), (401, 502), (503, 502)])
def test_dictate_maps_scribe_errors(client, upstream, code, expected):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(code, json={"message": "Failed"})
    assert client.post("/api/attachments/dictate", json=body()).status_code == expected

    def down(request):
        raise httpx.ConnectError("down")

    upstream.handler = down
    assert client.post("/api/attachments/audio", json=body()).status_code == 502
