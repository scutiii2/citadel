"""Internal account-scoped Skills page routes and account-deletion purge.

A plain HTTP route and not a tool, so no model can name a user or approve a skill: only
ember_api calls them for the signed-in account. This is the one place that reaches
`skill_store.set_status`. Checked against the internal token like /upload (an unset token
never validates).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import sqlite3
from dataclasses import asdict

from pydantic import BaseModel, ValidationError

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import settings
from src.services import capability_registry, skill_store

_UID = re.compile(r"[0-9a-f]{32}")


def _token_valid(request: Request) -> bool:
    expected = settings.internal_api_token
    provided = request.headers.get("X-Internal-Token", "")
    if not expected:
        return False
    return hmac.compare_digest(expected, provided)


def _skills_online() -> bool:
    return "skills" in capability_registry.names() and capability_registry.is_enabled("skills")


class StatusBody(BaseModel):
    status: str


class EditBody(BaseModel):
    title: str
    when_to_use: str
    steps: str
    tools: str = ""


def _view(skill: skill_store.Skill) -> dict:
    """The JSON shape of a skill. `failing` is the store's rule, so no client has to repeat it."""
    return {**asdict(skill), "failing": skill_store.is_failing(skill)}


def _refuse(request: Request) -> JSONResponse | None:
    """The shared gate: token, capability switch and uid shape."""
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)
    if not _skills_online():
        return JSONResponse({"error": "Skills is not enabled"}, status_code=404)
    if not _UID.fullmatch(request.path_params["uid"]):
        return JSONResponse({"error": "Not a valid account uid"}, status_code=400)
    return None


async def owner_skills(request: Request) -> Response:
    """Internal page API. Only ember_api may choose an owner; never an MCP tool."""
    if (refusal := _refuse(request)) is not None:
        return refusal
    uid = request.path_params["uid"]
    skill_id = request.path_params.get("skill_id")
    path = settings.skills_db_path
    try:
        if request.method == "GET":
            skills = await asyncio.to_thread(skill_store.list_skills, path, uid)
            return JSONResponse([_view(skill) for skill in skills])
        if request.method == "DELETE":
            removed = await asyncio.to_thread(skill_store.delete, path, uid, skill_id)
            return Response(status_code=204) if removed else JSONResponse({"error": "Skill not found"}, status_code=404)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"error": "Expected JSON"}, status_code=415)
        body = StatusBody.model_validate(await request.json())
        if body.status not in skill_store.STATUSES:
            return JSONResponse({"error": "Unknown status"}, status_code=422)
        if not await asyncio.to_thread(skill_store.set_status, path, uid, skill_id, body.status):
            return JSONResponse({"error": "Skill not found"}, status_code=404)
        skills = await asyncio.to_thread(skill_store.list_skills, path, uid)
        skill = next((s for s in skills if s.id == skill_id), None)
        return JSONResponse(_view(skill)) if skill else JSONResponse({"error": "Skill not found"}, status_code=404)
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse({"error": "Invalid request: send a status"}, status_code=422)
    except skill_store.SkillStoreError as error:
        return JSONResponse({"error": str(error)}, status_code=409)
    except (sqlite3.Error, OSError):
        return JSONResponse({"error": "Skill storage is unavailable"}, status_code=503)


async def edit_skill(request: Request) -> Response:
    """Rewrite a skill's text. The status stays and the success/failure counts reset."""
    if (refusal := _refuse(request)) is not None:
        return refusal
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return JSONResponse({"error": "Expected JSON"}, status_code=415)
    try:
        body = EditBody.model_validate(await request.json())
        skill = await asyncio.to_thread(
            skill_store.update, settings.skills_db_path, request.path_params["uid"], request.path_params["skill_id"],
            body.title, body.when_to_use, body.steps, body.tools,
        )
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse({"error": "Invalid request: send title, when_to_use, steps and tools"}, status_code=422)
    except skill_store.SkillConflict as error:
        return JSONResponse({"error": str(error)}, status_code=409)
    except skill_store.SkillStoreError as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    except (sqlite3.Error, OSError):
        return JSONResponse({"error": "Skill storage is unavailable"}, status_code=503)
    return JSONResponse(_view(skill)) if skill else JSONResponse({"error": "Skill not found"}, status_code=404)


async def purge_skills_owner(request: Request) -> JSONResponse:
    if (refusal := _refuse(request)) is not None:
        return refusal
    purged = await asyncio.to_thread(skill_store.purge_owner, settings.skills_db_path, request.path_params["uid"])
    return JSONResponse({"purged": purged})


class _UidLogFilter(logging.Filter):
    """Keep the internal uid out of Uvicorn's request paths."""

    def filter(self, record: logging.LogRecord) -> bool:
        def redact(value):
            text = str(value)
            return re.sub(r"(/skills/owners/)[^\s\"?/]+", r"\1[redacted]", text) if "/skills/owners/" in text else value

        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        return True


def install_skill_routes(app: Starlette) -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _UidLogFilter) for f in access_logger.filters):
        access_logger.addFilter(_UidLogFilter())
    app.add_route("/skills/owners/{uid}", purge_skills_owner, methods=["DELETE"])
    app.add_route("/skills/owners/{uid}/skills", owner_skills, methods=["GET"])
    app.add_route("/skills/owners/{uid}/skills/{skill_id:int}", owner_skills, methods=["DELETE"])
    app.add_route("/skills/owners/{uid}/skills/{skill_id:int}", edit_skill, methods=["PUT"])
    app.add_route("/skills/owners/{uid}/skills/{skill_id:int}/status", owner_skills, methods=["PUT"])
