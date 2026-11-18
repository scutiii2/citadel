"""Audio for Bard's text-to-speech results; Bard owns every file.

Stronghold (`apps/stronghold/src/bard`) asks Bard for the speech and the voice list. The finished
file is streamed from here, with the browser's Range header, so Portcullis keeps that one route.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.bard import BardGateway
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/bard", tags=["bard"])
ID = r"^[0-9a-f]{32}$"


def gateway(request: Request) -> BardGateway:
    return BardGateway(request.app.state.upstream, request.app.state.settings.bard_url, request.app.state.bard_token)


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
    client: BardGateway = Depends(gateway),
):
    return await client.stream(file_id, account, range_header=request.headers.get("range"))
