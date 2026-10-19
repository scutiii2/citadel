"""Signed file downloads on armory's existing HTTP listener (no second service)."""
from __future__ import annotations

import asyncio
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from src.config import settings
from src.services import capability_registry
from src.services.internal_token import is_exposed_without_token
from src.services.video_downloads import get_runtime


async def download_video(request: Request):
    # Do not initialize a disabled capability or disclose the presence of a file.
    try:
        enabled = capability_registry.is_enabled("video")
    except KeyError:
        enabled = False
    if not enabled or is_exposed_without_token(settings.host, settings.internal_api_token):
        return JSONResponse({"error": "File not available"}, status_code=404)
    from src.capabilities.video_downloader.utils.errors import DownloaderError
    from src.capabilities.video_downloader.utils.store.names import content_disposition
    try:
        exp = int(request.query_params.get("exp", ""))
        sig = request.query_params.get("sig", "")
        file_id = request.path_params["file_id"]
        def resolve():
            async def operation(service):
                file = service.file_for_download(file_id, exp, sig)
                return file, service.file_path(file)
            return get_runtime().call(operation)
        file, path = await asyncio.to_thread(resolve)
    except (DownloaderError, ValueError, OverflowError):
        return JSONResponse({"error": "File not available"}, status_code=404)
    return FileResponse(path, media_type=file.mime, headers={
        "Content-Disposition": content_disposition(file.name),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    })
