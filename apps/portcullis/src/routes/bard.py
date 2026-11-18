"""Speech from Bard, through Stronghold: it holds Bard's connection and token, so Portcullis keeps none.

Stronghold (`apps/stronghold/src/bard`) asks Bard for the speech, the voice list and the finished audio file.
The file is streamed through here, with the browser's Range header, so the player can seek.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import StreamingResponse

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
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
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> StreamingResponse:
    range_header = request.headers.get("range")
    response = await stronghold.open_stream(
        f"/bard/audio/{file_id}", account, headers={"Range": range_header} if range_header else None)
    if response.status_code not in (200, 206):
        await response.aread()
        await response.aclose()
        if response.status_code in (404, 416):
            raise HTTPException(response.status_code, "The audio expired or is unavailable.")
        raise HTTPException(502, "Audio is unavailable; check Stronghold's Bard connection.")

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
