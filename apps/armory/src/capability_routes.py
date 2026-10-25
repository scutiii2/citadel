"""HTTP endpoints for built-in capabilities: status, live enable/disable, refresh; plain routes beside the MCP surface, not tools.
GET /capabilities, POST /capabilities/refresh, GET /capabilities/{name}/gui, PATCH /capabilities/{name} ``{"enabled": bool}`` (404/400/409 on unknown/bad body/import failure)."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import capability_gui
from src.services import capability_registry
from src.services.capability_loader import CapabilityError, CapabilityLoader


def _status_json(loader: CapabilityLoader, name: str) -> dict[str, object]:
    record = loader.record_for(name)
    known = name in capability_registry.names()
    return {
        "name": name,
        "enabled": known and capability_registry.is_enabled(name),
        "label": capability_registry.label(name) if known else (record.label if record else name),
        "tools": capability_registry.tool_names(name) if known else [],
        "resources": capability_registry.resource_names(name) if known else [],
        # True only when a valid page exists and the capability is on, so a link never leads to a 404.
        "has_gui": known and capability_gui.load_page(name) is not None,
        "load_error": record.load_error if record else None,
        "missing": record.missing if record else False,
        "loaded": record.loaded if record else known,
    }


def _all_names(loader: CapabilityLoader) -> list[str]:
    return sorted(set(capability_registry.names()) | {record.id for record in loader.records()})


def _list(loader: CapabilityLoader) -> JSONResponse:
    return JSONResponse([_status_json(loader, name) for name in _all_names(loader)])


def install_capability_routes(app: Starlette, loader: CapabilityLoader) -> None:
    """Add the capability status/toggle/refresh routes to an existing Starlette app."""

    async def list_capabilities(request: Request) -> JSONResponse:
        return _list(loader)

    async def refresh_capabilities(request: Request) -> JSONResponse:
        await loader.refresh()
        return _list(loader)

    async def capability_gui_page(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if name not in capability_registry.names():
            return JSONResponse({"error": f"Unknown capability {name!r}"}, status_code=404)
        page = capability_gui.load_page(name)
        if page is None:
            return JSONResponse({"error": f"Capability {name!r} has no page"}, status_code=404)
        return JSONResponse(page.model_dump(mode="json", exclude_none=True))

    async def update_capability(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if name not in _all_names(loader):
            return JSONResponse({"error": f"Unknown capability {name!r}"}, status_code=404)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - malformed JSON is a 400, not a 500
            return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            return JSONResponse({"error": "'enabled' (a boolean) is required"}, status_code=400)
        try:
            final_id = await loader.set_online(name, body["enabled"])
        except CapabilityError as error:
            return JSONResponse({"error": str(error)}, status_code=error.status)
        return JSONResponse(_status_json(loader, final_id))

    app.add_route("/capabilities", list_capabilities, methods=["GET"])
    app.add_route("/capabilities/refresh", refresh_capabilities, methods=["POST"])
    app.add_route("/capabilities/{name}/gui", capability_gui_page, methods=["GET"])
    app.add_route("/capabilities/{name}", update_capability, methods=["PATCH"])
