"""Internal account-scoped Memory page routes and account-deletion purge.
Plain HTTP, not tools, so no model can name a user; checked against the internal token."""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
import json
import sqlite3
from dataclasses import asdict

from pydantic import BaseModel, Field, ValidationError, field_validator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.responses import Response

from src.config import settings
from src.services import capability_registry
from src.capabilities.memory.utils import memory_store

_UID = re.compile(r"[0-9a-f]{32}")


def _token_valid(request: Request) -> bool:
    expected = settings.internal_api_token
    provided = request.headers.get("X-Internal-Token", "")
    if not expected:
        return False
    return hmac.compare_digest(expected, provided)


def _memory_online() -> bool:
    return "memory" in capability_registry.names() and capability_registry.is_enabled("memory")


class MemoryBody(BaseModel):
    text: str = Field(min_length=1, max_length=memory_store.MAX_NOTE_CHARS)

    @field_validator("text")
    @classmethod
    def clean_text(cls, text: str) -> str:
        clean = " ".join(text.split())
        if not clean:
            raise ValueError("Memory cannot be empty")
        return clean


class MemoryUpdate(MemoryBody):
    expected_text: str = Field(min_length=1, max_length=memory_store.MAX_NOTE_CHARS)


async def memory_notes(request: Request) -> Response:
    """Internal page API. Only ember_api may choose an owner; never an MCP tool."""
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)
    if not _memory_online():
        return JSONResponse({"error": "Memory is not enabled"}, status_code=404)
    uid = request.path_params["uid"]
    if not _UID.fullmatch(uid):
        return JSONResponse({"error": "Not a valid account uid"}, status_code=400)
    path = settings.memory_db_path
    note_id = request.path_params.get("note_id")
    try:
        if request.method == "GET":
            notes = await asyncio.to_thread(memory_store.search, path, uid, "", memory_store.MAX_NOTES)
            return JSONResponse([asdict(note) for note in notes])
        if request.method == "DELETE":
            removed = await asyncio.to_thread(memory_store.forget, path, uid, note_id)
            return Response(status_code=204) if removed else JSONResponse({"error": "Memory not found"}, status_code=404)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"error": "Expected JSON"}, status_code=415)
        body = await request.json()
        if request.method == "PUT":
            draft = MemoryUpdate.model_validate(body)
            note = await asyncio.to_thread(memory_store.update, path, uid, note_id, draft.text, draft.expected_text)
            return JSONResponse(asdict(note)) if note else JSONResponse({"error": "Memory not found"}, status_code=404)
        draft = MemoryBody.model_validate(body)
        outcome = await asyncio.to_thread(memory_store.save, path, uid, draft.text)
        notes = await asyncio.to_thread(memory_store.search, path, uid, "", memory_store.MAX_NOTES)
        note = next((note for note in notes if note.id == outcome.id), None)
        if note is None:
            return JSONResponse({"error": "Memory changed; reload and try again"}, status_code=409)
        return JSONResponse(asdict(note), status_code=201)
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse({"error": "Invalid memory: provide text of 1 to 500 characters"}, status_code=422)
    except memory_store.MemoryConflict as error:
        return JSONResponse({"error": str(error)}, status_code=409)
    except memory_store.MemoryStoreError as error:
        return JSONResponse({"error": str(error)}, status_code=409)
    except (sqlite3.Error, OSError):
        return JSONResponse({"error": "Memory storage is unavailable"}, status_code=503)


async def purge_memory_owner(request: Request) -> JSONResponse:
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)
    if not _memory_online():
        return JSONResponse({"error": "Memory is not enabled"}, status_code=404)
    uid = request.path_params["uid"]
    if not _UID.fullmatch(uid):
        return JSONResponse({"error": "Not a valid account uid"}, status_code=400)
    purged = await asyncio.to_thread(memory_store.purge_owner, settings.memory_db_path, uid)
    return JSONResponse({"purged": purged})


class _PurgeLogFilter(logging.Filter):
    """Keep the internal uid out of Uvicorn's request paths."""

    def filter(self, record: logging.LogRecord) -> bool:
        def redact(value):
            text = str(value)
            return re.sub(r"(/memory/owners/)[^\s\"?]+", r"\1[redacted]", text) if "/memory/owners/" in text else value

        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        return True


def install_memory_routes(app: Starlette) -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _PurgeLogFilter) for f in access_logger.filters):
        access_logger.addFilter(_PurgeLogFilter())
    app.add_route("/memory/owners/{uid}", purge_memory_owner, methods=["DELETE"])
    app.add_route("/memory/owners/{uid}/notes", memory_notes, methods=["GET", "POST"])
    app.add_route("/memory/owners/{uid}/notes/{note_id:int}", memory_notes, methods=["PUT", "DELETE"])
