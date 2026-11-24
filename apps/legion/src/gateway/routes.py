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
from src.gateway import trust
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


# Almost every upstream failure reaches the caller as 502; the Test result names what really went wrong instead.
TEST_CODES = {"gateway_auth": "401", "gateway_quota": "402", "gateway_rate_limit": "429", "gateway_refused": "4XX",
              "gateway_unavailable": "5XX", "gateway_unreachable": "NET", "gateway_timeout": "TIME", "gateway_bad_reply": "BAD"}


def _test_code(error: Any) -> str:
    return TEST_CODES.get(error.code, str(error.status))


def _parts(kind: str) -> tuple[Any, Any] | None:
    if kind == "conversation":
        return gateway.chat_service(), gateway.chat_store()
    if kind == "decision":
        return gateway.decision_service(), gateway.decision_store()
    return None


def _with_tiers(presets: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each chat preset that has a template file in gateways/<provider>/<name>.json also carries that file's tier models
    and descriptions, so choosing the preset fills the whole Models tab."""
    from src.providers import llm_config

    try:
        templates = llm_config.load_gateways()
    except (OSError, ValueError):
        return presets
    result = {}
    for key, preset in presets.items():
        block = templates.get(preset.get("provider"), {}).get(key)
        models = block.get("models") if isinstance(block, dict) else None
        if isinstance(models, dict):
            tiers = {name: tier for name, tier in models.items() if isinstance(tier, dict) and isinstance(tier.get("id"), str)}
            preset = {**preset,
                      "models": {name: tier["id"] for name, tier in tiers.items() if not tier["id"].startswith("{")},
                      "descriptions": {name: tier["use_for"] for name, tier in tiers.items() if isinstance(tier.get("use_for"), str)}}
        result[key] = preset
    return result


async def _agents_needing(gateway_id: str) -> list[str]:
    """Enabled agents that would have no trusted gateway left without this one (it is trusted now, or they could not
    be saved)."""
    from src.agents import agent_store
    from src.providers import gateway_client

    if not await asyncio.to_thread(gateway_client.is_trusted, gateway_id):
        return []
    return await asyncio.to_thread(agent_store.agents_losing_trust, gateway_id)


def _needs_message(agents: list[str]) -> str:
    return ("Every agent needs at least one trusted gateway. This is the only one of " + ", ".join(agents)
            + ": give them another trusted gateway first.")


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
            presets = {key: {**preset, "trusted": trust.conversation(key, preset)} for key, preset in _with_tiers(CONVERSATION_PRESETS).items()}
            return JSONResponse({"gateways": rows, "form": CONVERSATION_FORM, "presets": presets})
        presets = {key: {**preset, "trusted": trust.decision(key, preset)} for key, preset in DECISION_PRESETS.items()}
        return JSONResponse({"gateways": rows, "kinds": {k: DECISION_FORM[k] for k in DECISION_KINDS},
                             "presets": presets, "model_lists": MODEL_LISTS})

    @mcp.custom_route("/agents/model-gateways/{kind}/{gateway_id}", methods=["PUT", "DELETE"])
    async def entry(request: Request) -> JSONResponse:
        if (parts := _parts(request.path_params["kind"])) is None:
            return JSONResponse({"error": "unknown gateway"}, status_code=404)
        store, gid = parts[1], request.path_params["gateway_id"]
        if request.method == "DELETE":
            if request.path_params["kind"] == "conversation" and (agents := await _agents_needing(gid)):
                return JSONResponse({"error": _needs_message(agents)}, status_code=409)
            deleted = await asyncio.to_thread(store.delete, gid)
            _forget()
            return JSONResponse({"ok": True} if deleted else {"error": "No such gateway."}, status_code=200 if deleted else 404)
        try:
            data: Any = await request.json()
        except ValueError:
            data = None
        if request.path_params["kind"] == "conversation" and isinstance(data, dict) and data.get("trusted") is False:
            if agents := await _agents_needing(gid):
                return JSONResponse({"error": _needs_message(agents)}, status_code=409)
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
        gid = request.path_params["gateway_id"]
        try:
            data: Any = await request.json() if await request.body() else None
        except ValueError:
            data = None
        try:
            if data is None:  # no body: test the saved gateway
                message = await gateway.call(parts[0].test(gid))
            else:  # a body: test the form as filled in, before it is saved
                try:
                    entry = await asyncio.to_thread(parts[1].draft, gid, data)
                except ValueError as error:
                    return JSONResponse({"ok": False, "code": "422", "message": str(error)})
                message = await gateway.call(parts[0].test_entry(gid, entry))
        except (GatewayError, DecisionGatewayError) as error:  # each service raises its own class
            return JSONResponse({"ok": False, "code": _test_code(error), "message": error.message})
        return JSONResponse({"ok": True, "message": message})

    @mcp.custom_route("/agents/model-gateways/conversation/{gateway_id}/models", methods=["GET"])
    async def models(request: Request) -> JSONResponse:
        try:
            names = await gateway.call(gateway.chat_service().models(request.path_params["gateway_id"]))
        except GatewayError as error:
            return JSONResponse({"ok": False, "code": str(error.status), "message": error.message})
        return JSONResponse({"ok": True, "models": names})
