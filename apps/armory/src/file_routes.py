"""Reading stored files. Core routes: they work whichever capabilities are on."""

from __future__ import annotations

import asyncio
import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from src.citadel_auth import current_caller
from src.config import settings
from src.services.file_errors import FileError
from src.services.identity_context import current_uid
from src.services.service_auth import install_auth
from src.services.user_files import runtime as files_runtime

logger = logging.getLogger(__name__)


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _locate(find):
    """(path, record) of the file `find(files)` returns, looked up on the files loop. Blocking."""
    runtime = files_runtime.get_runtime(settings)

    async def perform():
        file = find(runtime.files)
        return runtime.files.path(file), file

    return runtime.call(perform())


async def _serve(find, respond) -> Response:
    try:
        path, file = await asyncio.to_thread(_locate, find)
    except FileError:
        return _error("File is not available", 404)
    except Exception:
        logger.exception("Reading a stored file failed")
        return _error("File storage is unavailable", 503)
    return respond(path, file)


async def file_content(request: Request) -> Response:
    if current_caller() is None:
        return _error("Missing authenticated service caller", 401)
    owner = current_uid()
    if not owner.strip():
        return _error("The requesting account is not identified", 400)
    file_id = request.path_params["file_id"]
    return await _serve(
        lambda files: files.get(file_id, owner),
        lambda path, file: FileResponse(path, media_type=file.mime, headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox", "Referrer-Policy": "no-referrer",
        }),
    )


async def file_download(request: Request) -> Response:
    sig = request.query_params.get("sig", "")
    try:
        exp = int(request.query_params.get("exp", ""))
    except ValueError:
        return _error("File is not available", 404)
    if not sig:
        return _error("File is not available", 404)
    file_id = request.path_params["file_id"]
    return await _serve(
        lambda files: files.file_for_download(file_id, exp, sig),
        lambda path, file: FileResponse(
            path, filename=file.name, media_type="application/octet-stream",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        ),
    )


def install_file_routes(app: Starlette) -> None:
    install_auth(app)
    app.add_route("/files/{file_id}/content", file_content, methods=["GET"])
    app.add_route("/files/{file_id}/download", file_download, methods=["GET"])
