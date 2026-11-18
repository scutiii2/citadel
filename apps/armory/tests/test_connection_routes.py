"""Exercise service assertions, requester ownership, and fixed upstream routes."""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.citadel_auth import settings_store
from src.services.service_auth import install_auth
from tests.auth_helpers import FreshHeaders


def setup_api(tmp_path, send):
    from src.connection_routes import install_connection_routes
    from src.services.connections import ConnectionStore

    store = ConnectionStore(tmp_path / "settings.db")
    for name in ("bard", "scribe", "reader"):
        store.update(name, {"rest": {"base_url": f"http://{name}.example",
                                    "auth": {"kind": "token", "token": "stored-secret"}}})
    app = Starlette()
    install_auth(app)
    install_connection_routes(app, store, httpx.AsyncClient(transport=httpx.MockTransport(send)))
    return store, TestClient(app)


@pytest.mark.parametrize(("route", "upstream", "kind"), [
    ("bard/speak", "/api/speak", "json"),
    ("bard/voices", "/api/voices", "get"),
    ("scribe/transcribe", "/api/transcribe", "file"),
    ("scribe/transcribe-partial", "/api/transcribe-partial", "file"),
    ("scribe/files", "/api/files", "file"),
    ("reader/files", "/api/files", "file"),
    ("reader/parse", "/api/parse", "json"),
])
def test_facade_uses_fixed_path_and_verified_requester(tmp_path, route, upstream, kind):
    def send(request):
        assert request.url.path == upstream
        assert request.url.host == route.split("/")[0] + ".example"
        assert request.headers["X-Internal-Token"] == "stored-secret"
        assert request.headers["X-Requester-Username"] == "ada"
        if kind == "file":
            assert request.headers["X-Filename"] == "recording.wav"
            assert request.content == b"content"
        return httpx.Response(200, json={"result": True})

    _, client = setup_api(tmp_path, send)
    headers = dict(FreshHeaders(uid="one", username="ada", caller="stronghold").items())
    headers["X-Requester-Username"] = "forged"
    if kind == "file":
        headers["X-Filename"] = "recording.wav"
        options = {"content": b"content"}
    elif kind == "json":
        options = {"json": {"text": "hello"} if route == "bard/speak" else {"file_id": "a" * 32}}
    else:
        options = {}
    with client:
        result = client.request("GET" if kind == "get" else "POST", "/connections/" + route,
                                headers=headers, **options)
    assert result.status_code == 200
    assert result.json() == {"result": True}


def test_range_and_allow_list(tmp_path):
    def send(request):
        assert request.headers["Range"] == "bytes=1-2"
        return httpx.Response(206, content=b"bc", headers={"Content-Range": "bytes 1-2/6"})

    _, client = setup_api(tmp_path, send)
    route = "/connections/bard/audio/" + "a" * 32
    with client:
        assert client.get(route, headers=FreshHeaders(caller="legion")).status_code == 403
        assert client.get(route, headers=FreshHeaders()).status_code == 401
        headers = dict(FreshHeaders(uid="one", username="ada").items())
        result = client.get(route, headers={**headers, "Range": "bytes=1-2"})
        assert result.status_code == 206
        assert result.headers["Content-Range"] == "bytes 1-2/6"
        assert result.content == b"bc"
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect("/connections/scribe/dictate",
                                          headers=dict(FreshHeaders(caller="legion").items())):
                pytest.fail("Legion connected to dictation")
        assert error.value.code == 4403


@pytest.mark.parametrize(("upstream_status", "status"), [(400, 400), (413, 413), (403, 502), (503, 502)])
def test_errors_keep_safe_status_and_hide_token(tmp_path, upstream_status, status):
    _, client = setup_api(tmp_path, lambda req: httpx.Response(
        upstream_status, json={"message": "rejected stored-secret"}))
    with client:
        result = client.get("/connections/bard/voices", headers=FreshHeaders(uid="one", username="ada"))
    assert result.status_code == status
    assert "stored-secret" not in result.text
    if upstream_status == 403:
        assert "Bard refused the token" in result.text


def test_migration_and_public_metadata(tmp_path):
    from src.services.connections import ConnectionStore

    path = tmp_path / "settings.db"
    settings_store.put(path, "extensions", "bard", {"label": "Bard", "url": "http://bard/mcp",
                       "headers": {"X-Internal-Token": "legacy-secret"}})
    store = ConnectionStore(path)
    views = store.views()
    assert [item["name"] for item in views] == ["bard", "scribe", "reader"]
    assert views[0]["class"] == "required"
    assert views[0]["mcp"]["auth"]["configured"] is True
    assert "legacy-secret" not in json.dumps(views)
    assert settings_store.read_all(path, "extensions") == {}
    with pytest.raises(ValueError):
        store.update("bard", {"rest": {"base_url": "http://bard/api",
                                      "auth": {"kind": "token", "token": "bad"}}})
    with pytest.raises(ValueError):
        store.remove("bard")


def test_dictation_enforces_bounds_and_one_stream_per_account(tmp_path, monkeypatch):
    from src.services import dictation

    class Remote:
        async def recv(self):
            await asyncio.Future()

        async def send(self, data):
            assert data == b"\x00\x00"

    @asynccontextmanager
    async def connect(uri, **options):
        assert uri == "ws://scribe.example/api/stream"
        assert options["additional_headers"]["X-Requester-Uid"] == "one"
        yield Remote()

    monkeypatch.setattr(dictation.websocket_client, "connect", connect)
    monkeypatch.setattr(dictation, "STREAM_MAX_BYTES", 2)
    _, client = setup_api(tmp_path, lambda request: pytest.fail("Unexpected HTTP request"))
    path = "/connections/scribe/dictate"
    def headers():
        return dict(FreshHeaders(uid="one", username="ada").items())
    with client:
        with client.websocket_connect(path, headers=headers()) as first:
            with client.websocket_connect(path, headers=headers()) as second:
                assert second.receive()["code"] == 1013
            first.send_bytes(b"\x00\x00")
            first.send_bytes(b"\x00\x00")
            assert first.receive()["code"] == 1009
        with client.websocket_connect(path, headers=headers()) as retry:
            retry.send_bytes(b"\0" * (dictation.STREAM_FRAME_BYTES + 2))
            assert retry.receive()["code"] == 1009


@pytest.mark.parametrize("message, code", [
    (b"x", 1008),
    ('{"type":"surprise"}', 1008),
    ('{"type":"stop","extra":true}', 1008),
    (None, 1011),
])
def test_armory_owns_dictation_validation_and_idle_timeout(tmp_path, monkeypatch, message, code):
    from src.services import dictation

    class Remote:
        async def recv(self):
            await asyncio.Future()

        async def send(self, _message):
            pytest.fail("Invalid frame reached the upstream")

    @asynccontextmanager
    async def connect(*args, **kwargs):
        yield Remote()

    monkeypatch.setattr(dictation.websocket_client, "connect", connect)
    if message is None:
        monkeypatch.setattr(dictation, "STREAM_IDLE_SECONDS", 0.05)
    _, client = setup_api(tmp_path, lambda request: pytest.fail("Unexpected HTTP request"))
    headers = dict(FreshHeaders(uid="one", username="ada").items())
    with client, client.websocket_connect("/connections/scribe/dictate", headers=headers) as socket:
        if isinstance(message, bytes):
            socket.send_bytes(message)
        elif isinstance(message, str):
            socket.send_text(message)
        assert socket.receive()["code"] == code
