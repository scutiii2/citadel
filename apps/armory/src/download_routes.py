"""GET /download?path=<id>: hands a caller a file a tool offered it; a plain route (like /upload), not a tool.
`path` is an opaque id from `services/downloads.py`; wrong token is 401, unknown, expired or foreign ids are the same 404."""

from __future__ import annotations

from urllib.parse import quote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import settings
from src.services import downloads
from src.services.identity_context import current_username
from src.citadel_auth import current_caller
from src.services.service_auth import install_auth


def _authenticated(request: Request) -> bool:
    return current_caller() is not None


async def download_file(request: Request) -> Response:
    if not _authenticated(request):
        return JSONResponse({"error": "Missing authenticated service caller"}, status_code=401)
    entry = downloads.registry.get(
        request.query_params.get("path", ""), current_username()
    )
    if entry is None:
        return JSONResponse({"error": "No such download (it may have expired)"}, status_code=404)
    return Response(
        entry.data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(entry.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


def install_download_routes(app: Starlette) -> None:
    install_auth(app)
    app.add_route("/download", download_file, methods=["GET"])
