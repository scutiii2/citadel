"""Legion's admin routes for the model gateway entries: list, save, delete, test and (chat gateway) list models.

`/agents/model-gateways/{kind}` where kind is `conversation` or `decision`. Secrets are write-only: the stores never
return them. Portcullis guards these paths with `agents.manage`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import gateway
from src.gateway.conversation.errors import GatewayError
from src.gateway.decision.errors import GatewayError as DecisionGatewayError
from src.gateway.conversation.presets import PRESETS as CONVERSATION_PRESETS
from src.gateway.conversation.store import FORM as CONVERSATION_FORM
from src.gateway.decision.presets import MODEL_LISTS, PRESETS as DECISION_PRESETS
from src.gateway.decision.store import KINDS as DECISION_KINDS

DECISION_FORM = {  # what the page shows per kind: (field, label, secret, required)
    "typesafe": [("url", "Address", False, False), ("model", "Model", False, True), ("api_key", "API key", True, True)],
    "ollama": [("url", "Ollama address", False, True), ("model", "Model", False, True)],
    "scuti": [("url", "Model service address", False, True), ("token", "Token", True, False),
              ("strategy", "Strategy", False, False), ("window", "Window (tokens)", False, False)],
    "freellmapi": [("url", "FreeLLMAPI address", False, True), ("model", "Decision model (empty: automatic)", False, False),
                   ("api_key", "API key", True, True)],
}


def _parts(kind: str) -> tuple[Any, Any] | None:
    if kind == "conversation":
        return gateway.chat_service(), gateway.chat_store()
    if kind == "decision":
        return gateway.decision_service(), gateway.decision_store()
    return None


def _forget() -> None:
    from src.providers import gateway_client
    from src.providers.decision import gateway_client as decision_client

    gateway_client.reset_cache()
    decision_client.reset_cache()


def register(mcp: FastMCP) -> None:
    @mcp.custom_route("/agents/model-gateways/{kind}", methods=["GET"])
    async def listing(request: Request) -> JSONResponse:
        kind = request.path_params["kind"]
        if (parts := _parts(kind)) is None:
            return JSONResponse({"error": "unknown gateway"}, status_code=404)
        rows = await gateway.call(parts[0].gateways())
        if kind == "conversation":
            return JSONResponse({"gateways": rows, "form": CONVERSATION_FORM, "presets": CONVERSATION_PRESETS})
        return JSONResponse({"gateways": rows, "kinds": {k: DECISION_FORM[k] for k in DECISION_KINDS},
                             "presets": DECISION_PRESETS, "model_lists": MODEL_LISTS})

    @mcp.custom_route("/agents/model-gateways/{kind}/{gateway_id}", methods=["PUT", "DELETE"])
    async def entry(request: Request) -> JSONResponse:
        if (parts := _parts(request.path_params["kind"])) is None:
            return JSONResponse({"error": "unknown gateway"}, status_code=404)
        store, gid = parts[1], request.path_params["gateway_id"]
        if request.method == "DELETE":
            deleted = await asyncio.to_thread(store.delete, gid)
            _forget()
            return JSONResponse({"ok": True} if deleted else {"error": "No such gateway."}, status_code=200 if deleted else 404)
        try:
            data: Any = await request.json()
        except ValueError:
            data = None
        try:
            saved = await asyncio.to_thread(store.put, gid, data)
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=422)
        _forget()
        return JSONResponse(saved)

    @mcp.custom_route("/agents/model-gateways/{kind}/{gateway_id}/test", methods=["POST"])
    async def test(request: Request) -> JSONResponse:
        if (parts := _parts(request.path_params["kind"])) is None:
            return JSONResponse({"error": "unknown gateway"}, status_code=404)
        try:
            message = await gateway.call(parts[0].test(request.path_params["gateway_id"]))
        except (GatewayError, DecisionGatewayError) as error:  # each service raises its own class
            return JSONResponse({"ok": False, "message": error.message})
        return JSONResponse({"ok": True, "message": message})

    @mcp.custom_route("/agents/model-gateways/conversation/{gateway_id}/models", methods=["GET"])
    async def models(request: Request) -> JSONResponse:
        try:
            names = await gateway.call(gateway.chat_service().models(request.path_params["gateway_id"]))
        except GatewayError as error:
            return JSONResponse({"ok": False, "message": error.message})
        return JSONResponse({"ok": True, "models": names})
