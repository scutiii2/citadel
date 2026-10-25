"""HTTP endpoints for `/help` and `/<capability> help`: GET /commands/help and /commands/help/{capability}.
Plain routes beside the MCP surface, not tools; chat_app's commands.py calls them instead of a tool (see capability_help.py)."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import capability_help
from src.services import capability_registry


async def get_help_index(request: Request) -> JSONResponse:
    return JSONResponse(capability_help.build_index())


async def get_help(request: Request) -> JSONResponse:
    capability_id = request.path_params["capability"]

    # Fail closed like command_routes.py: a disabled or unregistered capability's help is unreachable.
    try:
        enabled = capability_registry.is_enabled(capability_id)
    except KeyError:
        enabled = False
    if not enabled:
        return JSONResponse({"error": f"Unknown capability {capability_id!r}"}, status_code=404)

    target = request.query_params.get("target", "all")
    command = request.query_params.get("command")

    try:
        return JSONResponse(capability_help.build_help(capability_id, target=target, command=command))
    except capability_help.HelpError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def install_help_routes(app: Starlette) -> None:
    app.add_route("/commands/help", get_help_index, methods=["GET"])
    app.add_route("/commands/help/{capability}", get_help, methods=["GET"])
