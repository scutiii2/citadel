"""Bounded Scribe WebSocket relay, owned by Armory for each account."""

import asyncio
import json
import math

from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio import client as websocket_client
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

STREAM_MAX_BYTES = 16_000 * 2 * 150
STREAM_FRAME_BYTES = 64_000
STREAM_IDLE_SECONDS = 15
STREAM_FINAL_SECONDS = 120
STREAM_MAX_SECONDS = 270
_SEND_SECONDS = 10


class Refused(Exception):
    def __init__(self, code: int):
        self.code = code


class DictationRelay:
    def __init__(self):
        self._active: set[str] = set()

    async def stream(self, uid: str, origin: str, headers: dict[str, str], socket: WebSocket) -> None:
        if uid in self._active:
            await socket.accept()
            await socket.close(1013, "A dictation stream is already active")
            return
        self._active.add(uid)
        try:
            await socket.accept()
            await self._relay(origin, headers, socket)
        finally:
            self._active.discard(uid)

    async def _relay(self, origin, headers, socket):
        uri = ("wss" if origin.startswith("https:") else "ws") + origin[origin.index(":"):] + "/api/stream"
        code, reason = 1000, ""
        try:
            async with asyncio.timeout(STREAM_MAX_SECONDS):
                async with websocket_client.connect(uri, additional_headers=headers, open_timeout=10,
                        close_timeout=3, max_size=256 * 1024, max_queue=4, proxy=None) as remote:
                    tasks = [asyncio.create_task(self._upload(socket, remote)),
                             asyncio.create_task(self._download(socket, remote, headers["X-Internal-Token"]))]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
        except InvalidStatus as error:
            code, reason = 1011, "Dictation unavailable"
            if error.response.status_code in (401, 403):
                reason = "Scribe refused the token. Check Armory Admin."
        except ConnectionClosed as error:
            code = 1013 if error.rcvd and error.rcvd.code == 1013 else 1011
        except Refused as error:
            code = error.code
        except WebSocketDisconnect:
            return
        except (OSError, TimeoutError, WebSocketException, ValueError, TypeError, AttributeError):
            code = 1011
        try:
            await socket.close(code, reason or ("Dictation unavailable" if code == 1011 else ""))
        except (RuntimeError, WebSocketDisconnect):
            pass

    @staticmethod
    async def _upload(socket, remote):
        used = 0
        stopped = False
        while True:
            message = await asyncio.wait_for(socket.receive(), STREAM_FINAL_SECONDS if stopped else STREAM_IDLE_SECONDS)
            if message["type"] == "websocket.disconnect":
                return
            if stopped:
                raise Refused(1008)
            data = message.get("bytes")
            if data is not None:
                if len(data) > STREAM_FRAME_BYTES or used + len(data) > STREAM_MAX_BYTES:
                    raise Refused(1009)
                if not data or len(data) % 2:
                    raise Refused(1008)
                used += len(data)
            else:
                data = message.get("text") or ""
                if len(data) > 128:
                    raise Refused(1009)
                try:
                    if json.loads(data) != {"type": "stop"}:
                        raise Refused(1008)
                except ValueError:
                    raise Refused(1008) from None
                stopped = True
            await asyncio.wait_for(remote.send(data), _SEND_SECONDS)

    @staticmethod
    async def _download(socket, remote, token):
        while True:
            event = json.loads(await remote.recv())
            kind = event.get("type")
            if kind == "error":
                await asyncio.wait_for(socket.send_json({"type": "error", "message": "Dictation is unavailable. Try again."}), _SEND_SECONDS)
                return
            if kind not in ("partial", "final") or not isinstance(event.get("text"), str):
                raise ValueError("Invalid transcription event")
            clean = {"type": kind, "text": event["text"].replace(token, "[redacted]")}
            if kind == "final" and "duration_s" in event:
                duration = float(event["duration_s"])
                if not math.isfinite(duration) or duration < 0:
                    raise ValueError("Invalid duration")
                clean["duration_s"] = duration
            await asyncio.wait_for(socket.send_json(clean), _SEND_SECONDS)
            if kind == "final":
                return
