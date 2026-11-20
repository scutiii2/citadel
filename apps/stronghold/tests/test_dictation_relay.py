"""Preserve the dictation protocol and bounds behind Stronghold's signed socket."""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from src.citadel_auth.testing import signed
from src.tool_services import dictation
from tests.auth_helpers import identity

PATH = "/speech/dictate"


def signed_headers(auth_stack):
    return {**signed(auth_stack["portcullis"], "stronghold"), **identity()}


class Remote:
    def __init__(self):
        self.events = asyncio.Queue()

    async def recv(self):
        return await self.events.get()

    async def send(self, data):
        if data == '{"type":"stop"}':
            self.events.put_nowait(json.dumps({"type": "final", "text": "hello fake-tool-token", "duration_s": 1.0}))
        else:
            assert data == b"\x00\x00"


@pytest.fixture
def upstream(monkeypatch):
    @asynccontextmanager
    async def connect(uri, **options):
        assert uri == "ws://scribe.test/api/stream"
        assert options["additional_headers"] == {
            "X-Requester-Uid": "u-1", "X-Requester-Username": "ana",
            "X-Requester-Email": "ana@example.com", "X-Internal-Token": "fake-tool-token",
        }
        yield Remote()

    monkeypatch.setattr(dictation, "Connect", connect)


def test_signed_websocket_forwards_requester_and_redacts_the_transcript(client, auth_stack, upstream):
    with client.websocket_connect(PATH, headers=signed_headers(auth_stack)) as socket:
        socket.send_bytes(b"\x00\x00")
        socket.send_text('{"type":"stop"}')
        assert socket.receive_json() == {"type": "final", "text": "hello [redacted]", "duration_s": 1.0}


def test_dictation_enforces_bounds_and_one_stream_per_account(client, auth_stack, upstream, monkeypatch):
    monkeypatch.setattr(dictation, "STREAM_MAX_BYTES", 2)
    headers = signed_headers(auth_stack)
    with client.websocket_connect(PATH, headers=headers) as first:
        with client.websocket_connect(PATH, headers=headers) as second:
            assert second.receive()["code"] == 1013
        first.send_bytes(b"\x00\x00")
        first.send_bytes(b"\x00\x00")
        assert first.receive()["code"] == 1009
    with client.websocket_connect(PATH, headers=headers) as retry:
        retry.send_bytes(b"\0" * (dictation.STREAM_FRAME_BYTES + 2))
        assert retry.receive()["code"] == 1009


@pytest.mark.parametrize("message, code", [
    (b"x", 1008),
    ('{"type":"surprise"}', 1008),
    ('{"type":"stop","extra":true}', 1008),
    (None, 1011),
])
def test_stronghold_owns_dictation_validation_and_idle_timeout(client, auth_stack, upstream, monkeypatch, message, code):
    if message is None:
        monkeypatch.setattr(dictation, "STREAM_IDLE_SECONDS", 0.05)
    with client.websocket_connect(PATH, headers=signed_headers(auth_stack)) as socket:
        if isinstance(message, bytes):
            socket.send_bytes(message)
        elif isinstance(message, str):
            socket.send_text(message)
        assert socket.receive()["code"] == code


@pytest.mark.parametrize("refused", [True, False])
async def test_relay_reports_only_an_unreachable_handshake(monkeypatch, refused):
    class Socket:
        async def accept(self):
            pass

        async def receive(self):
            await asyncio.Future()

        async def send_json(self, value):
            assert value["type"] == "final"

        async def close(self, code, _reason):
            assert code == (1011 if refused else 1000)

    @asynccontextmanager
    async def connect(*_args, **_kwargs):
        if refused:
            raise OSError("unreachable")
        remote = Remote()
        remote.events.put_nowait('{"type":"final","text":"hello"}')
        yield remote

    monkeypatch.setattr(dictation, "Connect", connect)
    result = await dictation.DictationRelay().stream("u-1", "http://scribe.test", {"X-Internal-Token": "x"}, Socket())
    assert result is refused


def test_dictation_never_follows_a_redirect():
    error = RuntimeError("handshake redirect")
    assert dictation.Connect.process_redirect(None, error) is error


def test_a_signed_legion_caller_cannot_open_dictation(as_service):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as error:
        with as_service("legion").websocket_connect(PATH):
            pytest.fail("Legion connected to dictation")
    assert error.value.code == 4403


def test_a_refused_scribe_token_names_stronghold_admin(client, auth_stack, monkeypatch):
    from websockets.datastructures import Headers
    from websockets.exceptions import InvalidStatus
    from websockets.http11 import Response

    class RefusedConnection:
        async def __aenter__(self):
            raise InvalidStatus(Response(401, "Unauthorized", Headers()))

        async def __aexit__(self, *_args):
            pass

    monkeypatch.setattr(dictation, "Connect", lambda *_args, **_kwargs: RefusedConnection())
    with client.websocket_connect(PATH, headers=signed_headers(auth_stack)) as socket:
        close = socket.receive()
        assert close["code"] == 1011
        assert close["reason"] == "Scribe refused the token. Check Stronghold Admin."
