"""Open owned browser streams against Stronghold with service and requester assertions."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from websockets.asyncio import client as websocket_client
from websockets.exceptions import ConnectionClosed, WebSocketException

from src.citadel_auth import ServiceAuth, logical_url, sign_assertion
from src.models import Account
from src.services.service_auth import identity_headers

_FRAME_BYTES = 64_000
_CONTROL_BYTES = 128
_STREAM_SECONDS = 280
_FORWARD_SECONDS = 10
_SAFE_ERRORS = {
    "Configure Scribe in Stronghold Admin.",
    "Set the Scribe token in Stronghold Admin.",
    "Scribe is disabled in Stronghold Admin.",
    "Scribe refused the token. Check Stronghold Admin.",
    "Dictation is unavailable. Try again.",
}


class ToolStreams:
    def __init__(self, client: httpx.AsyncClient, catalog, identity):
        self.client = client
        self.catalog = catalog
        self.identity = identity

    def _headers(self, account: Account) -> dict[str, str]:
        return identity_headers(account.username, account.email, account.uid, identity=self.identity)

    async def open_audio(self, file_id: str, account: Account, range_header: str | None) -> httpx.Response:
        headers = {**self._headers(account), "Accept-Encoding": "identity"}
        if range_header:
            headers["Range"] = range_header
        url = f"{logical_url('stronghold')}/speech/audio/{file_id}"
        try:
            request = self.client.build_request("GET", url, headers=headers, timeout=120)
            return await self.client.send(request, stream=True, follow_redirects=False,
                                          auth=ServiceAuth(self.identity, "stronghold"))
        except httpx.HTTPError as error:
            raise HTTPException(502, "Stronghold is unreachable. Try again.") from error

    async def dictate(self, account: Account, browser: WebSocket, on_final: Callable[[int], Awaitable[None]]) -> None:
        target = urlsplit(self.catalog.url("stronghold"))
        uri = urlunsplit(("wss" if target.scheme == "https" else "ws", target.netloc,
                          "/speech/dictate", "", ""))
        headers = {**self._headers(account), "Authorization": "Bearer " + sign_assertion(self.identity, "stronghold")}
        total = 0

        async def upstream(remote):
            nonlocal total
            while True:
                incoming = await browser.receive()
                if incoming["type"] == "websocket.disconnect":
                    return
                data = incoming.get("bytes")
                if data is not None:
                    if len(data) > _FRAME_BYTES:
                        raise OversizeFrame
                    total += len(data)
                else:
                    data = incoming.get("text") or ""
                    if len(data.encode("utf-8")) > _CONTROL_BYTES:
                        raise OversizeFrame
                await asyncio.wait_for(remote.send(data), _FORWARD_SECONDS)

        async def downstream(remote):
            while True:
                event = json.loads(await remote.recv())
                kind = event.get("type")
                if kind == "error":
                    message = event.get("message")
                    if not isinstance(message, str) or message not in _SAFE_ERRORS:
                        message = "Dictation is unavailable. Try again."
                    await asyncio.wait_for(browser.send_json({"type": "error", "message": message}), _FORWARD_SECONDS)
                    return
                if kind not in ("partial", "final") or not isinstance(event.get("text"), str):
                    raise ValueError("Invalid dictation message.")
                message = {"type": kind, "text": event["text"]}
                if kind == "final":
                    if "duration_s" in event:
                        message["duration_s"] = event["duration_s"]
                    await on_final(total)
                await asyncio.wait_for(browser.send_json(message), _FORWARD_SECONDS)
                if kind == "final":
                    return

        code = 1000
        try:
            async with asyncio.timeout(_STREAM_SECONDS):
                async with websocket_client.connect(uri, additional_headers=headers, open_timeout=10,
                        close_timeout=3, max_size=256 * 1024, max_queue=4, proxy=None) as remote:
                    tasks = [asyncio.create_task(upstream(remote)), asyncio.create_task(downstream(remote))]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
        except ConnectionClosed as error:
            code = error.rcvd.code if error.rcvd and error.rcvd.code in (1000, 1008, 1009, 1013) else 1011
        except OversizeFrame:
            code = 1009
        except WebSocketDisconnect:
            return
        except (OSError, TimeoutError, WebSocketException, ValueError, TypeError, AttributeError):
            code = 1011
        try:
            await browser.close(code, "Dictation unavailable" if code == 1011 else "")
        except (RuntimeError, WebSocketDisconnect):
            pass


class OversizeFrame(Exception):
    """A browser frame exceeded the relay's transport limit."""
