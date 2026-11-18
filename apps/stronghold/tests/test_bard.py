"""/bard: speech and the installed voices, from Bard."""

from __future__ import annotations

from tests.auth_helpers import identity, caller, requester

import json

import httpx
import pytest
from fastapi.testclient import TestClient

FID = "a" * 32
ANONYMOUS = identity(uid="")


def down(_request):
    raise httpx.ConnectError("down")


def test_speak_and_voices_need_the_requester(client: TestClient, tools) -> None:
    assert client.post("/bard/speak", json={"text": "hi"}, headers=ANONYMOUS).status_code == 400
    assert client.get("/bard/voices", headers=ANONYMOUS).status_code == 400
    assert not tools["bard"].requests


def test_speak_and_installed_voices_are_asked_from_bard(client: TestClient, tools, platform) -> None:
    tools["bard"].handler = lambda r: httpx.Response(
        200, json={"voices": ["v2"]} if r.method == "GET" else {"file_id": FID, "duration_s": 1.5, "voice": "v2"})

    assert client.get("/bard/voices").json() == {"voices": ["v2"]}
    assert tools["bard"].requests[-1].url.path == "/api/voices"
    response = client.post("/bard/speak", json={"text": "hello", "voice": "v2"})

    assert response.status_code == 200
    assert response.json() == {"file_id": FID, "duration_s": 1.5, "voice": "v2"}
    sent = tools["bard"].requests[-1]
    assert sent.url.path == "/api/speak" and json.loads(sent.content) == {"text": "hello", "voice": "v2"}
    assert sent.headers["x-requester-username"] == "ana" and sent.headers["x-requester-uid"] == "u-1"
    assert platform.actions == [("u-1", "bard.speak", f"Generated speech file {FID}")]  # never the text


@pytest.mark.parametrize("code, expected", [(400, 400), (413, 413), (401, 502), (503, 502)])
def test_speak_maps_bard_failures(client: TestClient, tools, code: int, expected: int) -> None:
    tools["bard"].handler = lambda r: httpx.Response(code, json={"message": "Unable to speak"})

    response = client.post("/bard/speak", json={"text": "hi", "voice": "v2"})

    assert response.status_code == expected
    if expected == 400:
        assert "Unable to speak" in response.text


def test_speak_rejects_empty_or_invalid_input(client: TestClient, tools) -> None:
    for payload in [{}, {"text": ""}, {"text": "hi", "voice": ""}, {"text": 123}]:
        assert client.post("/bard/speak", json=payload).status_code == 422
    assert not tools["bard"].requests


def test_a_bard_outage_is_a_502(client: TestClient, tools) -> None:
    tools["bard"].handler = down

    assert client.get("/bard/voices").status_code == 502
    assert client.post("/bard/speak", json={"text": "hi", "voice": "v1"}).status_code == 502


def test_audio_streams_from_bard_with_identity_token_and_range(client: TestClient, tools) -> None:
    tools["bard"].handler = lambda r: httpx.Response(
        206, content=b"2345",
        headers={"content-type": "audio/mpeg", "content-range": "bytes 2-5/10", "accept-ranges": "bytes"})

    response = client.get(f"/bard/audio/{FID}", headers={"Range": "bytes=2-5"})

    assert response.status_code == 206 and response.content == b"2345"
    assert response.headers["content-type"] == "audio/mpeg" and response.headers["content-range"] == "bytes 2-5/10"
    sent = tools["bard"].requests[-1]
    assert sent.url.path == f"/api/files/{FID}" and sent.headers["range"] == "bytes=2-5"
    assert sent.headers["x-requester-username"] == "ana"


def test_audio_needs_the_requester_and_a_valid_id(client: TestClient, tools) -> None:
    assert client.get(f"/bard/audio/{FID}", headers=ANONYMOUS).status_code == 400
    assert client.get("/bard/audio/not-hex").status_code == 422
    assert not tools["bard"].requests


@pytest.mark.parametrize("code, expected", [(404, 404), (416, 416), (401, 502), (503, 502)])
def test_audio_maps_bard_failures(client: TestClient, tools, code: int, expected: int) -> None:
    tools["bard"].handler = lambda r: httpx.Response(code, json={"error": "x"})
    assert client.get(f"/bard/audio/{FID}").status_code == expected


def test_audio_with_bard_down_is_a_502(client: TestClient, tools) -> None:
    tools["bard"].handler = down
    assert client.get(f"/bard/audio/{FID}").status_code == 502
