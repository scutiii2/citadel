"""Uploads an attached audio file to Scribe, which owns it for 24 hours.

Scribe checks the owner from the identity headers; the browser never learns
Scribe's origin or the internal token."""
from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from websockets.asyncio import client as websocket_client
from websockets.exceptions import ConnectionClosed, WebSocketException

from src.models import Account
from src.services.mcp_session import identity_headers


class _StreamRefused(Exception):
    def __init__(self, code: int):
        self.code = code


# Mono 16kHz PCM16, at most 150 seconds. Awaited sends provide backpressure;
# websockets additionally bounds its upstream message queue and message size.
STREAM_MAX_BYTES = 16_000 * 2 * 150
STREAM_FRAME_BYTES = 64_000
STREAM_IDLE_SECONDS = 15
STREAM_FINAL_SECONDS = 120
STREAM_MAX_SECONDS = 270


class ScribeGateway:
    def __init__(self, client: httpx.AsyncClient, base_url: str, token: str | None):
        self.client, self.base, self.token = client, base_url.rstrip("/"), token

    async def upload(self, account: Account, filename: str, content: bytes) -> dict:
        return await self._audio_request("files", account, filename, content)

    async def transcribe(self, account: Account, filename: str, content: bytes) -> dict:
        """Transcribe through the same owner, quota and cache as attached audio."""
        return await self._audio_request("transcribe", account, filename, content)

    async def transcribe_partial(self, account: Account, filename: str, content: bytes) -> dict:
        return await self._audio_request("transcribe-partial", account, filename, content)

    async def stream(self, account: Account, browser: WebSocket,
                     on_final: Callable[[int], Awaitable[None]]) -> None:
        """Relay bounded PCM and draft events. Never relay upstream exceptions/reasons."""
        base = urlsplit(self.base)
        uri = urlunsplit(("wss" if base.scheme == "https" else "ws", base.netloc,
                          base.path + "/api/stream", "", ""))
        headers = identity_headers(account.username, account.email, self.token, account.uid)
        byte_count = 0

        async def upload(remote):
            nonlocal byte_count
            stopped = False
            while True:
                message = await asyncio.wait_for(browser.receive(),
                    STREAM_FINAL_SECONDS if stopped else STREAM_IDLE_SECONDS)
                if message["type"] == "websocket.disconnect":
                    return None
                if stopped:
                    raise _StreamRefused(1008)
                data = message.get("bytes")
                if data is not None:
                    if len(data) > STREAM_FRAME_BYTES or byte_count + len(data) > STREAM_MAX_BYTES:
                        raise _StreamRefused(1009)
                    if not data or len(data) % 2:
                        raise _StreamRefused(1008)
                    byte_count += len(data)
                    await asyncio.wait_for(remote.send(data), 10)
                else:
                    text = message.get("text", "")
                    if len(text) > 128:
                        raise _StreamRefused(1009)
                    if json.loads(text) != {"type": "stop"}:
                        raise _StreamRefused(1008)
                    stopped = True
                    await asyncio.wait_for(remote.send(json.dumps({"type": "stop"})), 10)

        async def download(remote):
            while True:
                event = json.loads(await remote.recv())
                kind = event.get("type")
                if kind == "error":
                    await asyncio.wait_for(browser.send_json({"type": "error", "message": "Dictation is unavailable. Try again."}), 10)
                    return None
                if kind not in ("partial", "final") or not isinstance(event.get("text"), str):
                    raise ValueError("Invalid transcription event")
                clean = {"type": kind, "text": event["text"]}
                if kind == "final" and "duration_s" in event:
                    duration = float(event["duration_s"])
                    if not math.isfinite(duration) or duration < 0:
                        raise ValueError("Invalid duration")
                    clean["duration_s"] = duration
                if kind == "final":
                    await on_final(byte_count)
                await asyncio.wait_for(browser.send_json(clean), 10)
                if kind == "final":
                    return byte_count

        code, result = 1000, None
        try:
            async with asyncio.timeout(STREAM_MAX_SECONDS):
                async with websocket_client.connect(uri, additional_headers=headers, open_timeout=10,
                        close_timeout=3, max_size=256 * 1024, max_queue=4, proxy=None) as remote:
                    tasks = [asyncio.create_task(upload(remote)), asyncio.create_task(download(remote))]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            value = task.result()
                            if value is not None:
                                result = value
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
        except ConnectionClosed as error:
            code = 1013 if error.rcvd and error.rcvd.code == 1013 else 1011
        except _StreamRefused as error:
            code = error.code
        except WebSocketDisconnect:
            return None
        except (OSError, TimeoutError, WebSocketException, ValueError, TypeError, AttributeError):
            code = 1011
        try:
            await browser.close(code, "Dictation unavailable" if code == 1011 else "")
        except (RuntimeError, WebSocketDisconnect):
            pass  # The browser may already have disconnected.
        return None

    async def _audio_request(self, endpoint: str, account: Account, filename: str, content: bytes) -> dict:
        headers = identity_headers(account.username, account.email, self.token, account.uid)
        headers["X-Filename"] = filename
        headers["Content-Type"] = "application/octet-stream"
        try:
            response = await self.client.post(f"{self.base}/api/{endpoint}", headers=headers, content=content, timeout=120)
        except httpx.HTTPError as error:
            raise HTTPException(502, "Scribe is unreachable. Try again.") from error
        if response.status_code == 200:
            return response.json()
        if response.status_code in (400, 413):
            try:
                message = response.json().get("message")
            except ValueError:
                message = None
            raise HTTPException(response.status_code, message or "Scribe rejected the audio.")
        raise HTTPException(502, "Scribe is unavailable; check its internal connection.")
