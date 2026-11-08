import asyncio
import json

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect
from starlette.websockets import WebSocket
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from tests.test_attachments_audio import body
from tests.test_permission_split import limited_account
from tests.test_registration import as_admin


PATH = '/api/attachments/dictate/stream'
ORIGIN = {'origin': 'http://testserver'}


class Remote:
    def __init__(self):
        self.sent = []
        self.opened = []
        self.closed = 0
        self.capacity = False

    def connect(self, uri, **kwargs):
        self.opened.append((uri, kwargs))
        return self

    async def __aenter__(self):
        self.events = asyncio.Queue()
        self.events.put_nowait(json.dumps({'type': 'partial', 'text': 'hello'}))
        return self

    async def __aexit__(self, *args):
        self.closed += 1

    async def send(self, message):
        self.sent.append(message)
        if isinstance(message, str):
            self.events.put_nowait(json.dumps({'type': 'final', 'text': 'hello world', 'duration_s': 1.5}))

    async def recv(self):
        if self.capacity:
            raise ConnectionClosedError(Close(1013, 'private internal origin'), Close(1013, ''), True)
        return await self.events.get()


@pytest.fixture
def remote(monkeypatch):
    remote = Remote()
    monkeypatch.setattr('websockets.asyncio.client.connect', remote.connect)
    return remote


def rejected(client, code, headers=ORIGIN):
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(PATH, headers=headers) as ws:
            ws.receive_json()
    assert error.value.code == code


def test_stream_requires_cookie(client, remote):
    rejected(client, 4401)
    assert not remote.opened


@pytest.mark.parametrize('origin', [None, 'null', 'https://evil.example', 'http://testserver.evil', 'http://testserver/path', 'https://testserver'])
def test_stream_requires_same_origin(client, remote, origin):
    as_admin(client)
    rejected(client, 4403, {} if origin is None else {'origin': origin})
    assert not remote.opened


def test_stream_requires_upload_permission(client, email, remote):
    limited_account(client, email, 'chat.use')
    rejected(client, 4403)
    assert not remote.opened


def test_stream_proxies_pcm_stop_transcripts_and_identity(client, remote):
    as_admin(client)
    client.app.state.internal_token = 'test-private-token'
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        assert ws.receive_json() == {'type': 'partial', 'text': 'hello'}
        ws.send_bytes(b'\x00\x01' * 320)
        ws.send_json({'type': 'stop'})
        assert ws.receive_json() == {'type': 'final', 'text': 'hello world', 'duration_s': 1.5}
    assert remote.sent == [b'\x00\x01' * 320, '{"type": "stop"}']
    uri, options = remote.opened[0]
    assert uri.endswith('/api/stream') and uri.startswith('ws://')
    headers = {key.lower(): value for key, value in options['additional_headers'].items()}
    assert headers['x-requester-username'] == 'root'
    assert 'test-private-token' in headers.values()
    assert 'origin' not in headers and 'cookie' not in headers
    actor = client.get('/api/auth/me').json()['id']
    logs = client.get('/api/logs/action', params={'actor': actor}).json()
    assert any(row['source'] == 'attachments.dictate' and '640 bytes' in row['message']
               and 'hello' not in row['message'] for row in logs)


def test_stream_limit_releases_after_disconnect(client, remote):
    as_admin(client)
    with client.websocket_connect(PATH, headers=ORIGIN) as first:
        first.receive_json()
        rejected(client, 1013)
        assert len(remote.opened) == 1
    with client.websocket_connect(PATH, headers=ORIGIN) as second:
        assert second.receive_json()['type'] == 'partial'


def test_capacity_close_reaches_browser_without_private_reason(client, remote):
    as_admin(client)
    remote.capacity = True
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1013
        assert 'private' not in error.value.reason


@pytest.mark.parametrize('payload', [b'x' * 65538, b'x', {'type': 'surprise'}, {'type': 'stop', 'extra': True}],
                         ids=['oversized', 'odd-pcm', 'unknown-command', 'extra-stop-keys'])
def test_stream_rejects_bad_frames(client, remote, payload):
    as_admin(client)
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.receive_json()
        if isinstance(payload, bytes):
            ws.send_bytes(payload)
        else:
            ws.send_json(payload)
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code in (1008, 1009)
    assert not remote.sent


def test_partial_transcription_identity_validation_and_no_retention(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={'text': 'hello', 'duration_s': 2.5})
    result = client.post('/api/attachments/dictate/partial', json=body('../speech.webm'))
    assert result.status_code == 200
    assert result.json() == {'text': 'hello', 'duration_s': 2.5}
    sent = upstream.requests[-1]
    assert sent.url.path == '/api/transcribe-partial'
    assert sent.content == b'abc' and sent.headers['x-filename'] == 'speech.webm'
    assert sent.headers['x-requester-username'] == 'root'
    upstream.requests.clear()
    assert client.post('/api/attachments/dictate/partial', json=body('x.exe')).status_code == 400
    assert client.post('/api/attachments/dictate/partial', json={'filename': 'x.webm', 'data': '!!!'}).status_code == 400
    assert not upstream.requests


def test_partial_requires_login_and_upload_permission(client, email, upstream):
    assert client.post('/api/attachments/dictate/partial', json=body()).status_code == 401
    limited_account(client, email, 'chat.use')
    upstream.requests.clear()
    assert client.post('/api/attachments/dictate/partial', json=body()).status_code == 403
    assert not upstream.requests


def test_stream_bounds_total_pcm_and_idle_time(client, remote, monkeypatch):
    as_admin(client)
    monkeypatch.setattr('src.services.scribe.STREAM_MAX_BYTES', 4)
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.receive_json()
        ws.send_bytes(b'abcdef')
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1009
    assert not remote.sent
    monkeypatch.setattr('src.services.scribe.STREAM_IDLE_SECONDS', 0.01)
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1011


def test_secure_stream_accepts_matching_https_origin(client, remote):
    as_admin(client)
    with client.websocket_connect('wss://testserver' + PATH, headers={'origin': 'https://testserver'}) as ws:
        assert ws.receive_json()['type'] == 'partial'


def test_stream_never_relays_upstream_error_details(client, remote):
    as_admin(client)
    original_enter = remote.__class__.__aenter__

    async def enter(self):
        await original_enter(self)
        self.events.get_nowait()
        self.events.put_nowait(json.dumps({'type': 'error', 'message': 'http://private-scribe token=secret'}))
        return self

    from unittest.mock import patch
    with patch.object(Remote, '__aenter__', enter):
        with client.websocket_connect(PATH, headers=ORIGIN) as ws:
            event = ws.receive_json()
            assert event['type'] == 'error'
            assert 'private-scribe' not in str(event) and 'secret' not in str(event)


def test_socket_task_cancellation_drains_relays_and_releases_account(client, remote):
    as_admin(client)
    cookie = client.cookies.get('ember_session')

    async def cancel_connection():
        from src.routes.attachments import dictate_stream

        incoming = asyncio.Queue()
        incoming.put_nowait({'type': 'websocket.connect'})
        partial = asyncio.Event()

        async def send(message):
            if message['type'] == 'websocket.send':
                partial.set()

        socket = WebSocket({
            'type': 'websocket', 'scheme': 'ws', 'path': PATH, 'query_string': b'',
            'headers': [(b'host', b'testserver'), (b'origin', b'http://testserver'),
                        (b'cookie', ('ember_session=' + cookie).encode())],
            'app': client.app,
        }, incoming.get, send)
        before = asyncio.all_tasks()
        task = asyncio.create_task(dictate_stream(socket))
        await asyncio.wait_for(partial.wait(), 2)
        task.cancel()
        await asyncio.wait_for(task, 2)
        assert not client.app.state.dictation_accounts
        assert not [pending for pending in asyncio.all_tasks() - before if not pending.done()]

    client.portal.call(cancel_connection)
    assert remote.closed == 1
