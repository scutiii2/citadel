"""Relays the dictation WebSocket to Scribe.

Scribe checks the owner from the identity headers; the browser never learns
Scribe's origin or the internal token. Stronghold sends it attached and dictated audio files."""
from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio import client as websocket_client
from websockets.exceptions import ConnectionClosed, WebSocketException

from src.models import Account
from src.services.service_auth import tool_headers


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

    async def stream(self, account: Account, browser: WebSocket,
                     on_final: Callable[[int], Awaitable[None]]) -> None:
        """Relay bounded PCM and draft events. Never relay upstream exceptions/reasons."""
        base = urlsplit(self.base)
        uri = urlunsplit(("wss" if base.scheme == "https" else "ws", base.netloc,
                          base.path + "/api/stream", "", ""))
        headers = tool_headers(account.username, account.email, self.token, account.uid)
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
