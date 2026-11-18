"""Signed, bounded REST and dictation routes for the three required services."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from src.citadel_auth import current_requester
from src.services.connections import REQUIRED, ConnectionStore, auth_headers, ready_status
from src.services.dictation import DictationRelay

MAX_FILE = 20 * 1024 * 1024
MAX_AUDIO = 64 * 1024 * 1024
MAX_JSON = 1024 * 1024
READ_SECONDS = 15
REQUEST_SECONDS = 120
_FILE_ID = re.compile(r"[0-9a-f]{32}")
_CONTENT_RANGE = re.compile(r"bytes [0-9]+-[0-9]+/(?:[0-9]+|\*)")


class RouteError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status


async def read_body(request: Request, limit: int) -> bytes:
    try:
        async with asyncio.timeout(READ_SECONDS):
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    raise RouteError(413, "Request is too large.")
                body.extend(chunk)
            return bytes(body)
    except TimeoutError:
        raise RouteError(408, "Request body timed out.") from None
    except ClientDisconnect:
        raise RouteError(400, "Request body was interrupted.") from None


async def read_json(response: httpx.Response) -> dict:
    data = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65536):
        if len(data) + len(chunk) > MAX_JSON:
            raise ValueError("Response is too large.")
        data.extend(chunk)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Response is not an object.")
    return value


def requester_headers() -> dict[str, str]:
    who = current_requester()
    if who is None or not who.username:
        raise RouteError(401, "Requester identity is required.")
    return {"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid}


@dataclass(frozen=True)
class ToolOperation:
    service: str
    upstream: str
    body: str | None = None


OPERATIONS = {
    "/connections/bard/speak": ToolOperation("bard", "/api/speak", "json"),
    "/connections/bard/voices": ToolOperation("bard", "/api/voices"),
    "/connections/scribe/transcribe": ToolOperation("scribe", "/api/transcribe", "file"),
    "/connections/scribe/transcribe-partial": ToolOperation("scribe", "/api/transcribe-partial", "file"),
    "/connections/scribe/files": ToolOperation("scribe", "/api/files", "file"),
    "/connections/reader/files": ToolOperation("reader", "/api/files", "file"),
    "/connections/reader/parse": ToolOperation("reader", "/api/parse", "json"),
}


class ConnectionRoutes:
    """Translate only named Citadel features into upstream requests."""

    def __init__(self, store: ConnectionStore, client: httpx.AsyncClient):
        self.store = store
        self.client = client
        self.dictation = DictationRelay()

    async def target(self, name: str) -> tuple[str, dict[str, str]]:
        headers = requester_headers()
        record = await asyncio.to_thread(self.store.get, name)
        state = ready_status(record)
        if not state["ready"]:
            raise RouteError(502, state["reason"])
        rest = record["rest"]
        return rest["base_url"], {**headers, **auth_headers(rest["auth"]), "Accept-Encoding": "identity"}

    async def status(self, request: Request) -> JSONResponse:
        records = await asyncio.to_thread(self.store.records)
        return JSONResponse({name: ready_status(records[name]) for name in REQUIRED})

    async def invoke(self, request: Request) -> JSONResponse:
        operation = OPERATIONS[request.url.path]
        try:
            origin, headers = await self.target(operation.service)
            body = None
            if operation.body == "file":
                filename = request.headers.get("x-filename", "")
                if (not filename or len(filename) > 255 or filename in {".", ".."}
                        or any(c in "/\\" or ord(c) < 32 or ord(c) > 126 for c in filename)):
                    raise RouteError(400, "Send a valid filename.")
                headers.update({"X-Filename": filename, "Content-Type": "application/octet-stream"})
                body = await read_body(request, MAX_FILE)
            elif operation.body == "json":
                limit = 4096 if operation.service == "reader" else MAX_JSON
                body = await read_body(request, limit)
                try:
                    fields = json.loads(body)
                except (ValueError, UnicodeError):
                    raise RouteError(400, "Send a valid JSON object.") from None
                if not isinstance(fields, dict):
                    raise RouteError(400, "Send a valid JSON object.")
                if operation.service == "reader" and not _valid_id(fields.get("file_id")):
                    raise RouteError(400, "Send an uploaded file ID.")
                headers["Content-Type"] = "application/json"
            async with asyncio.timeout(REQUEST_SECONDS):
                async with self.client.stream(request.method, origin + operation.upstream, headers=headers,
                                              content=body, timeout=REQUEST_SECONDS, follow_redirects=False) as remote:
                    if remote.status_code != 200:
                        raise await self.refusal(operation.service, remote, headers)
                    result = await read_json(remote)
                    return JSONResponse(_redacted(result, headers["X-Internal-Token"]))
        except RouteError as error:
            return _error(error)
        except (ValueError, UnicodeError):
            return _error(RouteError(502, f"{REQUIRED[operation.service]} sent an invalid response."))
        except (httpx.HTTPError, TimeoutError):
            return _error(RouteError(502, f"{REQUIRED[operation.service]} is unreachable. Try again."))

    @staticmethod
    async def refusal(name: str, remote: httpx.Response, headers: dict[str, str]) -> RouteError:
        label, status = REQUIRED[name], remote.status_code
        if status in (401, 403):
            return RouteError(502, f"{label} refused the token. Check Armory Admin.")
        if status in (400, 413) or (name == "reader" and status == 422):
            message = None
            try:
                message = (await read_json(remote)).get("message")
            except (ValueError, httpx.HTTPError):
                pass
            token = headers["X-Internal-Token"]
            detail = message.replace(token, "[redacted]") if isinstance(message, str) and message else f"{label} refused the request."
            return RouteError(413 if status == 413 else 400, detail[:500])
        return RouteError(502, f"{label} is unavailable. Try again.")

    async def audio(self, request: Request):
        file_id = request.path_params["file_id"]
        if not _valid_id(file_id):
            return _error(RouteError(404, "Audio file not found."))
        try:
            origin, headers = await self.target("bard")
            if value := request.headers.get("range"):
                if len(value) > 256:
                    raise RouteError(416, "Invalid audio range.")
                headers["Range"] = value
            outbound = self.client.build_request("GET", f"{origin}/api/files/{file_id}", headers=headers, timeout=READ_SECONDS)
            async with asyncio.timeout(READ_SECONDS):
                remote = await self.client.send(outbound, stream=True, follow_redirects=False)
            if remote.status_code not in (200, 206):
                await remote.aclose()
                if remote.status_code in (404, 416):
                    raise RouteError(remote.status_code, "The audio expired or is unavailable.")
                raise await self.refusal("bard", remote, headers)
            length = remote.headers.get("content-length")
            if length is not None and (not length.isdecimal() or int(length) > MAX_AUDIO):
                await remote.aclose()
                raise RouteError(502, "Bard audio exceeds the stream limit.")
            kept = {"content-type": "audio/mpeg"}
            if length is not None:
                kept["content-length"] = length
            if remote.headers.get("accept-ranges") == "bytes":
                kept["accept-ranges"] = "bytes"
            if _CONTENT_RANGE.fullmatch(remote.headers.get("content-range", "")):
                kept["content-range"] = remote.headers["content-range"]
            return StreamingResponse(_audio_chunks(remote), status_code=remote.status_code, headers=kept,
                                     background=BackgroundTask(remote.aclose))
        except RouteError as error:
            return _error(error)
        except (httpx.HTTPError, TimeoutError):
            return _error(RouteError(502, "Bard is unreachable. Try again."))

    async def dictate(self, socket: WebSocket) -> None:
        requester = current_requester()
        if requester is None or not requester.username:
            await socket.close(4401)
            return
        try:
            origin, headers = await self.target("scribe")
        except RouteError as error:
            await socket.accept()
            await socket.send_json({"type": "error", "message": str(error)})
            await socket.close(1011)
            return
        await self.dictation.stream(requester.uid, origin, headers, socket)


async def _audio_chunks(remote: httpx.Response):
    try:
        remaining = MAX_AUDIO
        async with asyncio.timeout(REQUEST_SECONDS):
            async for chunk in remote.aiter_bytes(chunk_size=65536):
                if len(chunk) > remaining:
                    raise RuntimeError("Bard audio exceeded the stream limit.")
                remaining -= len(chunk)
                yield chunk
    finally:
        await remote.aclose()


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_FILE_ID.fullmatch(value))


def _redacted(value, token):
    if isinstance(value, str):
        return value.replace(token, "[redacted]")
    if isinstance(value, dict):
        return {_redacted(key, token): _redacted(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item, token) for item in value]
    return value


def _error(error: RouteError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, error.status)


def install_connection_routes(app: Starlette, store: ConnectionStore, client: httpx.AsyncClient) -> ConnectionRoutes:
    routes = ConnectionRoutes(store, client)
    for path, operation in OPERATIONS.items():
        app.add_route(path, routes.invoke, methods=["POST" if operation.body else "GET"])
    app.add_route("/connections/status", routes.status)
    app.add_route("/connections/bard/audio/{file_id}", routes.audio)
    app.router.routes.append(WebSocketRoute("/connections/scribe/dictate", routes.dictate))
    return routes
