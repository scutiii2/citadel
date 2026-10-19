"""HTTP endpoint for the chat-invocable command registry: GET /commands.

Mounted the same way extension_routes.py's /extensions is (see run.py):
a plain HTTP route alongside the MCP surface, not a tool - chat_app's
command execution/autocomplete path polls this, no model ever calls
it.
"""

from __future__ import annotations

import asyncio

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from src import commands
from src.services import capability_registry


def _spec_json(spec: commands.CommandSpec) -> dict[str, str]:
    return {
        "capability": spec.capability,
        "name": spec.name,
        "description": spec.description,
        "tool_name": spec.tool_name,
    }


def _is_capability_enabled(name: str) -> bool:
    # A command whose capability the registry has never heard of (should
    # only happen in a test that registers a command directly, never for
    # a real capability - run.py's capturing() covers every one of
    # those) fails open, same "absent means enabled" rule
    # app_config.capability_enabled() already applies to the config file.
    try:
        return capability_registry.is_enabled(name)
    except KeyError:
        return True


async def list_commands(request: Request) -> JSONResponse:
    return JSONResponse(
        [_spec_json(spec) for spec in commands.all_commands() if _is_capability_enabled(spec.capability)]
    )


async def download_pdf(request: Request) -> FileResponse | JSONResponse:
    """Redeem a signed bearer link without requiring the internal API token."""
    try:
        enabled = capability_registry.is_enabled("pdf")
    except KeyError:
        enabled = False
    if not enabled:
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)

    try:
        from src.capabilities.pdf_merger import domain
        from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError
    except ImportError:
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)

    unavailable = JSONResponse({"error": "File is not available"}, status_code=404)
    try:
        exp = int(request.query_params.get("exp", ""))
    except ValueError:
        return unavailable
    sig = request.query_params.get("sig", "")
    if not sig:
        return unavailable
    try:
        path, filename = await asyncio.to_thread(
            domain.download, request.path_params["file_id"], exp, sig
        )
        return FileResponse(
            path, filename=filename, media_type="application/octet-stream",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    except domain.PdfError:
        return unavailable
    except MergerError as error:
        if error.code != ErrorCode.INTERNAL:
            return unavailable
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)
    except Exception:
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)


def install_command_routes(app: Starlette) -> None:
    app.add_route("/commands", list_commands, methods=["GET"])
    app.add_route("/pdf/files/{file_id}/download", download_pdf, methods=["GET"])
    from contextlib import asynccontextmanager
    import asyncio
    from src.video_routes import download_video
    from src.services.video_downloads import close_runtime

    app.add_route("/video/files/{file_id}/download", download_video, methods=["GET"])
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as state:
            try:
                yield state
            finally:
                await asyncio.to_thread(close_runtime)

    app.router.lifespan_context = lifespan
