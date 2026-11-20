"""Bard, Scribe and Reader over REST, from the connections Stronghold holds. Moved from Armory's connection_routes.py."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from src.citadel_auth import UnknownService, current_requester
from src.tool_services.store import REQUIRED, ToolStore, ready_status, token_for

MAX_FILE = 20 * 1024 * 1024
MAX_JSON = 1024 * 1024
READ_SECONDS = 15
REQUEST_SECONDS = 120
COOLDOWN_SECONDS = 30.0
REMEMBERED_FILES = 2000
_FILE_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class Feature:
    service: str
    upstream: str
    method: str = "POST"
    body: str | None = None  # "json" | "file" | None


FEATURES = {
    "/connections/bard/speak": Feature("bard", "/api/speak", "POST", "json"),
    "/connections/bard/voices": Feature("bard", "/api/voices", "GET"),
    "/connections/scribe/transcribe": Feature("scribe", "/api/transcribe", "POST", "file"),
    "/connections/scribe/transcribe-partial": Feature("scribe", "/api/transcribe-partial", "POST", "file"),
    "/connections/scribe/files": Feature("scribe", "/api/files", "POST", "file"),
    "/connections/reader/files": Feature("reader", "/api/files", "POST", "file"),
    "/connections/reader/parse": Feature("reader", "/api/parse", "POST", "json"),
}
AUDIO = Feature("bard", "/api/files/{file_id}", "GET")


def valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_FILE_ID.fullmatch(value))


def _redacted(value, token: str):
    if isinstance(value, str):
        return value.replace(token, "[redacted]") if token else value
    if isinstance(value, dict):
        return {_redacted(key, token): _redacted(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item, token) for item in value]
    return value


class ToolServices:
    def __init__(self, store: ToolStore, client: httpx.AsyncClient, resolve_origin: Callable[[str], str],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._store, self._client, self._resolve, self._clock = store, client, resolve_origin, clock
        self._down: dict[tuple[str, str], float] = {}
        self._files: OrderedDict[tuple[str, str, str], str] = OrderedDict()

    def _mark_down(self, name: str, origin_id: str) -> None:
        now = self._clock()
        self._down = {key: until for key, until in self._down.items() if until > now}
        self._down[(name, origin_id)] = now + COOLDOWN_SECONDS

    def _remember(self, name: str, uid: str, file_id: str, origin_id: str) -> None:
        key = (name, uid, file_id)
        self._files[key] = origin_id
        self._files.move_to_end(key)
        if len(self._files) > REMEMBERED_FILES:
            self._files.popitem(last=False)

    def _candidates(self, name: str, record: dict, uid: str, file_id: str | None) -> list[dict]:
        if file_id is not None:
            origin_id = self._files.get((name, uid, file_id))
            return [origin for origin in record["origins"] if origin["origin_id"] == origin_id]
        now = self._clock()
        return [origin for origin in record["origins"] if self._down.get((name, origin["origin_id"]), 0.0) <= now]

    async def _ready_record(self, name: str) -> dict:
        record = await asyncio.to_thread(self._store.get, name)
        state = ready_status(name, record)
        if not state["ready"]:
            raise HTTPException(502, state["reason"])
        return record

    @staticmethod
    def _unreachable(name: str) -> HTTPException:
        return HTTPException(502, f"[1002] {REQUIRED[name]} is unreachable. Try again.")

    async def _send(
        self, feature: Feature, *, deadline: float, content: bytes | None = None,
        headers: dict[str, str] | None = None, file_id: str | None = None,
    ) -> tuple[httpx.Response, str, str, str]:
        """Return the open upstream response with its origin, sent token and requester UID."""
        name = feature.service
        record = await self._ready_record(name)
        who = current_requester()
        if who is None or not who.username:
            raise HTTPException(400, "Missing requester identity")
        candidates = self._candidates(name, record, who.uid, file_id)
        if file_id is not None and not candidates:
            raise HTTPException(404, "File not found.")
        for origin in candidates:
            origin_id = origin["origin_id"]
            try:
                address = self._resolve(origin_id)
            except (KeyError, UnknownService):
                continue
            token = token_for(record, origin)
            sent = {"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid,
                    "X-Internal-Token": token, "Accept-Encoding": "identity", **(headers or {})}
            try:
                timeout = READ_SECONDS if feature is AUDIO else httpx.Timeout(REQUEST_SECONDS, connect=READ_SECONDS)
                request = self._client.build_request(feature.method, address + feature.upstream.format(file_id=file_id or ""),
                                                     headers=sent, content=content, timeout=timeout)
                async with asyncio.timeout_at(deadline):
                    response = await self._client.send(request, stream=True, follow_redirects=False)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                self._mark_down(name, origin_id)
                continue
            except (httpx.TransportError, TimeoutError):
                self._mark_down(name, origin_id)
                raise self._unreachable(name) from None
            except (httpx.HTTPError, ValueError):
                raise HTTPException(502, f"{REQUIRED[name]} is unavailable. Try again.") from None
            return response, origin_id, token, who.uid
        raise self._unreachable(name)

    async def _refusal(self, name: str, response: httpx.Response, token: str) -> HTTPException:
        label, status = REQUIRED[name], response.status_code
        if status in (401, 403):
            return HTTPException(502, f"{label} refused the token. Check Stronghold Admin.")
        if status in (400, 413) or (name == "reader" and status == 422):
            message = None
            try:
                message = (await _read_json(response)).get("message")
            except ValueError:
                pass
            detail = message.replace(token, "[redacted]") if isinstance(message, str) and message and token else None
            return HTTPException(413 if status == 413 else 400, (detail or f"{label} refused the request.")[:500])
        return HTTPException(502, f"{label} is unavailable. Try again.")

    async def _finish(
        self, feature: Feature, response: httpx.Response, origin_id: str, token: str, uid: str, *, deadline: float,
    ) -> dict:
        name = feature.service
        try:
            async with asyncio.timeout_at(deadline):
                if response.status_code != 200:
                    raise await self._refusal(name, response, token)
                result = await _read_json(response)
            file_id = result.get("file_id")
            if valid_id(file_id):
                self._remember(name, uid, file_id, origin_id)
            return _redacted(result, token)
        except (httpx.TransportError, TimeoutError):
            self._mark_down(name, origin_id)
            raise self._unreachable(name) from None
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, f"{REQUIRED[name]} sent an invalid response.") from None
        finally:
            await response.aclose()

    async def call(self, method: str, path: str, body: dict | None = None) -> dict:
        feature = FEATURES[path]
        content = None
        headers = {}
        file_id = None
        if feature.body == "json":
            content = json.dumps(body or {}).encode()
            if len(content) > (4096 if feature.service == "reader" else MAX_JSON):
                raise HTTPException(413, "Request is too large.")
            headers["Content-Type"] = "application/json"
            if feature.service == "reader":
                file_id = (body or {}).get("file_id")
                if not valid_id(file_id):
                    raise HTTPException(400, "Send an uploaded file ID.")
        deadline = asyncio.get_running_loop().time() + REQUEST_SECONDS
        response = await self._send(feature, deadline=deadline, content=content, headers=headers, file_id=file_id)
        return await self._finish(feature, *response, deadline=deadline)

    async def post_file(self, path: str, filename: str, content: bytes) -> dict:
        feature = FEATURES[path]
        if (not filename or len(filename) > 255 or filename in {".", ".."}
                or any(c in "/\\" or ord(c) < 32 or ord(c) > 126 for c in filename)):
            raise HTTPException(400, "Send a valid filename.")
        if len(content) > MAX_FILE:
            raise HTTPException(413, "Request is too large.")
        deadline = asyncio.get_running_loop().time() + REQUEST_SECONDS
        response = await self._send(
            feature, deadline=deadline, content=content,
            headers={"X-Filename": filename, "Content-Type": "application/octet-stream"})
        return await self._finish(feature, *response, deadline=deadline)

    async def stream_target(self, name: str) -> tuple[str, str, dict[str, str]]:
        """The first healthy origin and the headers a stream to it needs (the token is never logged)."""
        record = await self._ready_record(name)
        who = current_requester()
        if who is None or not who.username:
            raise HTTPException(400, "Missing requester identity")
        for origin in self._candidates(name, record, who.uid, None):
            try:
                address = self._resolve(origin["origin_id"])
            except (KeyError, UnknownService):
                continue
            return origin["origin_id"], address, {"X-Requester-Username": who.username, "X-Requester-Email": who.email,
                             "X-Requester-Uid": who.uid, "X-Internal-Token": token_for(record, origin)}
        raise self._unreachable(name)

    def mark_down(self, name: str, origin_id: str) -> None:
        self._mark_down(name, origin_id)

    async def open_audio(self, file_id: str, range_header: str | None) -> httpx.Response:
        """The audio file as an open stream the caller must close. Only the origin that made it can serve it."""
        if not valid_id(file_id):
            raise HTTPException(404, "Audio file not found.")
        if range_header is not None and len(range_header) > 256:
            raise HTTPException(416, "Invalid audio range.")
        deadline = asyncio.get_running_loop().time() + READ_SECONDS
        response, origin_id, _, _ = await self._send(
            AUDIO, deadline=deadline, file_id=file_id, headers={"Range": range_header} if range_header else None)
        response.extensions["tool_service_origin_id"] = origin_id
        return response


async def _read_json(response: httpx.Response) -> dict:
    data = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65536):
        if len(data) + len(chunk) > MAX_JSON:
            raise ValueError("Response is too large.")
        data.extend(chunk)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Response is not an object.")
    return value
