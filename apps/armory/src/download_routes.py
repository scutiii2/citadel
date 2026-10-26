"""GET /download?path=<id>: hands a caller a file a tool offered it; a plain route (like /upload), not a tool.
`path` is an opaque id from `services/downloads.py`; wrong token is 401, unknown, expired or foreign ids are the same 404."""

from __future__ import annotations

import hmac
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import settings
from src.services import downloads
from src.services.identity_context import REQUESTER_USERNAME_HEADER


def _token_valid(request: Request) -> bool:
    """An unset token never validates (not even against an empty header)."""
    expected = settings.internal_api_token
    if not expected:
        return False
    return hmac.compare_digest(expected, request.headers.get("X-Internal-Token", ""))


async def download_file(request: Request) -> Response:
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)
    entry = downloads.registry.get(
        request.query_params.get("path", ""), request.headers.get(REQUESTER_USERNAME_HEADER, "")
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
    app.add_route("/download", download_file, methods=["GET"])
