"""Stronghold handles Bard speech, voices and audio streams."""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import StreamingResponse

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.tool_streams import ToolStreams
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/bard", tags=["bard"])
ID = r"^[0-9a-f]{32}$"


_FORWARDED = ("content-type", "content-length", "content-range", "accept-ranges")


@router.post("/speak")
async def speak(
    request: Request,
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/bard/speak")


@router.get("/voices")
async def voices(
    request: Request,
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/bard/voices")


@router.get("/audio/{file_id}")
async def audio(
    request: Request,
    file_id: str = Path(pattern=ID),
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
) -> StreamingResponse:
    state = request.app.state
    streams = ToolStreams(state.upstream, state.catalog, state.keyring)
    response = await streams.open_audio(file_id, account, request.headers.get("range"))
    if response.status_code not in (200, 206):
        try:
            if response.status_code in (404, 416):
                raise HTTPException(response.status_code, "The audio expired or is unavailable.")
            if response.status_code == 502:
                body = bytearray()
                try:
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if len(body) + len(chunk) > 4096:
                            break
                        body.extend(chunk)
                    detail = json.loads(body).get("detail")
                except (ValueError, AttributeError):
                    detail = None
                if isinstance(detail, str) and detail:
                    raise HTTPException(502, detail)
            raise HTTPException(502, "Bard audio is unavailable. Check Stronghold Admin, Tool services.")
        finally:
            await response.aclose()

    async def chunks():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()

    headers = {k: v for k, v in response.headers.items() if k.lower() in _FORWARDED}
    headers.update({
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": 'inline; filename="bard.mp3"',
    })
    return StreamingResponse(chunks(), status_code=response.status_code, headers=headers)
