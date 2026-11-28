"""Tool services: status for Portcullis, the audio and dictation streams, and the admin API behind Portcullis."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.citadel_auth import current_caller, current_requester
from src.requester import Requester, current_requester as requester_dependency
from src.tool_services.client import ToolServices, _read_json, valid_id
from src.tool_services.outside import OutsideError, OutsideRegistry, valid_token
from src.tool_services.store import REQUIRED, ToolStore, ready_status, token_for, view

MAX_AUDIO = 64 * 1024 * 1024
STREAM_SECONDS = 120
ADMIN_SAVE_SECONDS = 18
_CONTENT_RANGE = re.compile(r"bytes [0-9]+-[0-9]+/(?:[0-9]+|\*)")

router = APIRouter(tags=["tool-services"])


def _services(request: Request) -> ToolServices:
    return request.app.state.connections


def _store(request: Request) -> ToolStore:
    return request.app.state.tool_store


def _outside(request: Request) -> OutsideRegistry:
    return request.app.state.outside


def _admin() -> None:
    caller = current_caller()
    if caller is None or caller.name != "portcullis":
        raise HTTPException(403, "only Portcullis may change tool services")


async def _admin_body(request: Request) -> dict:
    _admin()
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(422, "Send a JSON object.") from None
    if not isinstance(body, dict):
        raise HTTPException(422, "Send a JSON object.")
    return body


def _known(name: str) -> str:
    if name not in REQUIRED:
        raise HTTPException(404, "No such tool service.")
    return name


@router.get("/tool-services/status")
async def status(store: ToolStore = Depends(_store), outside: OutsideRegistry = Depends(_outside)) -> dict:
    records = await asyncio.to_thread(store.records)
    return {name: ready_status(name, record, outside.origin_address) for name, record in records.items()}


@router.get("/speech/audio/{file_id}")
async def audio(file_id: str, request: Request, services: ToolServices = Depends(_services),
                _who: Requester = Depends(requester_dependency)):
    if not valid_id(file_id):
        raise HTTPException(404, "Audio file not found.")
    remote = await services.open_audio(file_id, request.headers.get("range"))
    if remote.status_code not in (200, 206):
        await remote.aclose()
        if remote.status_code in (404, 416):
            raise HTTPException(remote.status_code, "The audio expired or is unavailable.")
        raise HTTPException(502, "Bard audio is unavailable. Check Stronghold Admin, Tool services.")
    length = remote.headers.get("content-length")
    if length is not None and (not length.isdecimal() or int(length) > MAX_AUDIO):
        await remote.aclose()
        raise HTTPException(502, "Bard audio exceeds the stream limit.")
    kept = {"content-type": "audio/mpeg"}
    if length is not None:
        kept["content-length"] = length
    if remote.headers.get("accept-ranges") == "bytes":
        kept["accept-ranges"] = "bytes"
    if _CONTENT_RANGE.fullmatch(remote.headers.get("content-range", "")):
        kept["content-range"] = remote.headers["content-range"]
    return StreamingResponse(_audio_chunks(remote, services), status_code=remote.status_code, headers=kept,
                             background=BackgroundTask(remote.aclose))


async def _audio_chunks(remote: httpx.Response, services: ToolServices) -> AsyncIterator[bytes]:
    try:
        remaining = MAX_AUDIO
        async with asyncio.timeout(STREAM_SECONDS):
            async for chunk in remote.aiter_bytes(chunk_size=65536):
                if len(chunk) > remaining:
                    raise RuntimeError("Bard audio exceeded the stream limit.")
                remaining -= len(chunk)
                yield chunk
    except (httpx.TransportError, TimeoutError):
        services.mark_down("bard", remote.extensions["tool_service_origin_id"])
        raise RuntimeError("Bard audio stream was interrupted.") from None
    finally:
        await remote.aclose()


@router.websocket("/speech/dictate")
async def dictate(socket: WebSocket) -> None:
    app = socket.app
    who = current_requester()
    if who is None or not who.username:
        await socket.close(4401)
        return
    services: ToolServices = app.state.connections
    try:
        origin_id, origin, headers = await services.stream_target("scribe")
    except HTTPException as error:
        await socket.accept()
        await socket.send_json({"type": "error", "message": str(error.detail)})
        await socket.close(1011)
        return
    unreachable = await app.state.dictation.stream(who.uid, origin, headers, socket)
    if unreachable:
        services.mark_down("scribe", origin_id)


@router.get("/admin/tool-services")
async def admin_list(store: ToolStore = Depends(_store), outside: OutsideRegistry = Depends(_outside)) -> dict:
    _admin()
    return {"services": [view(name, record, outside.origin_address) for name, record in store.records().items()]}


@router.post("/admin/tool-services/lookup")
async def admin_lookup(body: dict = Depends(_admin_body), outside: OutsideRegistry = Depends(_outside)) -> dict:
    address = body.get("address")
    if not isinstance(address, str):
        raise HTTPException(400, "body must be {address}")
    try:
        return await outside.lookup(address)
    except OutsideError as error:
        raise HTTPException(error.status, str(error)) from None


@router.put("/admin/tool-services/{name}")
async def admin_save(name: str, request: Request, body: dict = Depends(_admin_body),
                     store: ToolStore = Depends(_store), outside: OutsideRegistry = Depends(_outside)) -> dict:
    name = _known(name)
    token = body.get("token")
    if "token" in body and (not isinstance(token, str) or not valid_token(token)):
        raise HTTPException(400, "The token must be a valid HTTP header value.")
    enabled = body.get("enabled")
    if "enabled" in body and not isinstance(enabled, bool):
        raise HTTPException(400, "enabled must be a boolean.")
    try:
        # Leave time for the SQLite write before Portcullis's 30-second read timeout.
        async with asyncio.timeout(ADMIN_SAVE_SECONDS) as preparation, request.app.state.tool_settings_lock:
            record = await asyncio.to_thread(store.get, name)
            if "addresses" in body:
                try:
                    entry = await outside.entry_from_addresses(body["addresses"], record)
                except OutsideError as error:
                    raise HTTPException(error.status, str(error)) from None
                await request.app.state.catalog.refresh()
                if any(outside.origin_address(origin["origin_id"]) is None for origin in entry["origins"]):
                    raise HTTPException(502, "[1002] Treasury is unavailable. Nothing was saved.")
                record = {**record, **entry}
            if enabled is not None:
                record["enabled"] = enabled
            if token:
                record["token"] = token
            preparation.reschedule(None)
            await asyncio.to_thread(store.put, name, record)
    except TimeoutError:
        raise HTTPException(502, "[1002] Treasury is unavailable. Nothing was saved.") from None
    return view(name, record, outside.origin_address)


@router.delete("/admin/tool-services/{name}")
async def admin_clear(name: str, request: Request, store: ToolStore = Depends(_store),
                      outside: OutsideRegistry = Depends(_outside)) -> dict:
    _admin()
    name = _known(name)
    async with request.app.state.tool_settings_lock:
        await asyncio.to_thread(store.clear, name)
        record = await asyncio.to_thread(store.get, name)
    return view(name, record, outside.origin_address)


@router.post("/admin/tool-services/{name}/test")
async def admin_test(name: str, request: Request, store: ToolStore = Depends(_store),
                     outside: OutsideRegistry = Depends(_outside)) -> dict:
    """Per origin: the health route, then one authenticated read that creates nothing."""
    _admin()
    name = _known(name)
    record = await asyncio.to_thread(store.get, name)
    state = ready_status(name, record)
    if not state["ready"]:
        return {"ok": False, "code": "SETUP", "message": state["reason"], "origins": []}
    who = current_requester()
    if who is None or not who.username:
        raise HTTPException(400, "Missing requester identity")
    headers = {"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid}
    http: httpx.AsyncClient = request.app.state.tool_http
    check = {"bard": ("GET", "/api/voices", 200, None), "scribe": ("POST", "/api/transcribe?voice_gate=invalid", 422, "bad_voice_gate"),
             "reader": ("POST", "/api/parse", 422, "invalid_request")}[name]
    results = []
    for origin in record["origins"]:
        address = outside.origin_address(origin["origin_id"])
        token = token_for(record, origin)
        if address is None:
            results.append({"origin_id": origin["origin_id"], "ok": False, "code": "GONE", "message": "This address left Treasury's catalog."})
            continue
        results.append({"origin_id": origin["origin_id"], **await _probe(http, address, {**headers, "X-Internal-Token": token}, check, name == "reader")})
    ok = all(result["ok"] for result in results)
    failed = next((result for result in results if not result["ok"]), None)
    return {"ok": ok, "message": "Every address is ready." if ok else "Some addresses are not ready.",
            **({"code": failed["code"]} if failed else {}), "origins": results}


async def _probe(http: httpx.AsyncClient, address: str, headers: dict[str, str],
                 check: tuple[str, str, int, str | None], json_body: bool) -> dict:
    method, path, expected, error_code = check
    try:
        async with asyncio.timeout(10):
            async with http.stream("GET", address + "/health", headers={"X-Internal-Token": headers["X-Internal-Token"]},
                                   follow_redirects=False) as health:
                if health.status_code in (401, 403):
                    return {"ok": False, "code": str(health.status_code), "message": "The token was refused."}
                if not health.is_success:
                    return {"ok": False, "code": str(health.status_code), "message": f"Health returned HTTP {health.status_code}."}
                if path.startswith("/api/transcribe") and (await _read_json(health)).get("ready") is False:
                    return {"ok": False, "code": "NOT_READY", "message": "Scribe is not ready. Check its speech engine configuration."}
            async with http.stream(method, address + path, headers=headers, json={} if json_body else None,
                                   follow_redirects=False) as answer:
                if answer.status_code in (401, 403):
                    return {"ok": False, "code": str(answer.status_code), "message": "The token was refused."}
                if answer.status_code == expected and (not error_code or (await _read_json(answer)).get("error") == error_code):
                    return {"ok": True, "message": "Ready."}
                return {"ok": False, "code": str(answer.status_code), "message": f"The authenticated check returned HTTP {answer.status_code}."}
    except TimeoutError:
        return {"ok": False, "code": "TIME", "message": "No answer within 10 seconds."}
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "code": "NET", "message": "Unreachable."}
