"""Token-protected deterministic brain gateway; independent of user tool opt-in."""
import asyncio
import hmac
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse

from src.config import settings
from src.capabilities.obsidian import domain
from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError
from src.capabilities.obsidian.utils import brain_resolver


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    operation: Literal["test", "status", "list", "read", "search", "write", "append", "retire"]
    scope: Literal["instance", "personal", "both"]
    path: str = Field(default="", max_length=500)
    query: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=40_000)
    top_k: int = Field(default=5, ge=1, le=20)
    candidate: dict | None = Field(default=None, repr=False)
    revision: int | None = None
    generation: str | None = None


def execute(body: Operation, uid: str):
    if body.operation == "retire":
        from src.capabilities.obsidian.utils.brain_indexes import indexes
        indexes.retire(uid, body.scope)
        return {"status": "retired"}
    if body.operation == "search":
        from src.capabilities.obsidian.utils.brain_operations import search
        return search(body.scope, body.query, body.top_k, uid).model_dump()
    if body.scope == "both":
        raise ObsidianGatewayError("Choose a single destination for this operation")
    if body.operation == "test":
        if not body.candidate or body.candidate.get("scope") != body.scope or body.candidate.get("source") != "remote":
            raise ObsidianGatewayError("Invalid connection test")
        snapshot = body.candidate
    else:
        snapshot = brain_resolver.resolve(body.scope, body.operation, uid)
    if body.revision is not None and body.revision != snapshot["revision"] or (
        body.generation is not None and body.generation != snapshot["generation"]):
        raise ObsidianGatewayError("Destination changed. Review the publication again.", status=409)
    gateway = brain_resolver.gateway(snapshot)
    if body.operation in {"status", "test"}:
        gateway.list("")
        from src.capabilities.obsidian.utils.brain_indexes import indexes
        return {"status": "connected", "scope": body.scope, "revision": snapshot["revision"],
                "generation": snapshot["generation"], "index_status": indexes.status(snapshot),
                "message": "Read-only connection test succeeded"}
    if body.operation == "list":
        result = domain.Vault(gateway).list_folder(body.path)
    elif body.operation == "read":
        # Raw text is returned to the authenticated API for hash reconciliation;
        # the browser renders Markdown with its existing sanitizing component.
        return {"path": body.path, "content": gateway.read(body.path), "scope": body.scope,
                "connection_label": snapshot["label"]}
    elif body.operation == "write":
        gateway.require_create_only()
        gateway.write(body.path, body.text, overwrite=False)
        return {"path": body.path, "success": True, "message": "Published a new Obsidian document"}
    else:
        gateway.append(body.path, body.text)
        return {"path": body.path, "success": True, "message": "Appended to Obsidian document"}
    return {**result.model_dump(), "scope": body.scope, "connection_label": snapshot["label"]}


async def operate(request):
    token = request.headers.get("X-Internal-Token", "")
    uid = request.headers.get("X-Requester-Uid", "")
    if not settings.internal_api_token or not hmac.compare_digest(token, settings.internal_api_token) or not uid:
        return JSONResponse({"error": "Valid internal authentication and requester required"}, status_code=401)
    raw = await request.body()
    if len(raw) > 200_000:
        return JSONResponse({"error": "Brain request too large"}, status_code=413)
    try:
        body = Operation.model_validate_json(raw)
        return JSONResponse(await asyncio.to_thread(execute, body, uid))
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse({"error": "Invalid brain operation"}, status_code=422)
    except ObsidianGatewayError as error:
        return JSONResponse({"error": str(error)}, status_code=error.status or 503)
    except (ValueError, OSError):
        return JSONResponse({"error": "Brain operation is unavailable"}, status_code=503)


def install_brain_routes(app):
    app.add_route("/brains/operation", operate, methods=["POST"])
