"""/api/attachments: files attached to a chat question (files.upload), and dictation.

Portcullis checks the login and the permission. Stronghold (`apps/stronghold/src/attachments`)
reads the text, sends PDFs and tables to Armory, audio to Scribe and documents to Reader. What stays
here is what must be streamed: an attachment's content for the preview and the dictation WebSocket.

The file comes base64-encoded in JSON: every POST to portcullis is JSON
(see json_only.py), which keeps cross-site form posts out."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Path, Request, Response, WebSocket

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.armory_streams import ArmoryStreams
from src.services.capability_files import CapabilityFilesGateway
from src.services.permissions import FILES_UPLOAD
from src.services.session_service import SessionService
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

require_chat = require_permission(FILES_UPLOAD)


@router.get("/files/{file_id}/content")
async def attachment_content(
    request: Request,
    file_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,100}$"),
    account: Account = Depends(require_permission("files.download")),
):
    """Preview an owned chat attachment without a PDF workspace subscription."""
    client = CapabilityFilesGateway(request.app.state.upstream, request.app.state.catalog.mcp_url(),
                                    request.app.state.keyring)
    return await client.stream("pdf", file_id, account, content=True, range_header=request.headers.get("range"))

@router.post("/text")
async def attachment_text(request: Request, account: Account = Depends(require_chat),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/attachments/text")


@router.post("/table")
async def attachment_table(request: Request, account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    """Armory keeps the whole file as a table for the data tools."""
    return await pass_on(request, stronghold, account, "/attachments/table")


@router.post("/pdf")
async def attachment_pdf(request: Request, account: Account = Depends(require_chat),
                         stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/attachments/pdf")


@router.post("/audio")
async def attachment_audio(request: Request, account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/attachments/audio")


@router.post("/document")
async def attachment_document(request: Request, account: Account = Depends(require_chat),
                              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/attachments/document")


@router.post("/dictate")
async def dictate(request: Request, account: Account = Depends(require_chat),
                  stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/attachments/dictate")


@router.post("/dictate/partial")
async def dictate_partial(request: Request, account: Account = Depends(require_chat),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/attachments/dictate/partial")


BEARER_PROTOCOL = "ember.bearer"


@router.websocket("/dictate/stream")
async def dictate_stream(websocket: WebSocket):
    """PCM stream; Scribe stays private. A browser is same-origin and sends its cookie. The Windows app
    (a configured desktop origin) cannot, so it offers its session token as the subprotocol pair
    `ember.bearer, <token>` (a WebSocket cannot carry an Authorization header)."""
    try:
        origin = urlsplit(websocket.headers.get("origin", ""))
        same_origin = (origin.scheme == ("https" if websocket.url.scheme == "wss" or getattr(websocket.state, "https", False) else "http") and origin.netloc
                       and origin.netloc.lower() == websocket.headers.get("host", "").lower()
                       and not origin.path and not origin.query and not origin.fragment
                       and not origin.username and not origin.password)
    except ValueError:
        same_origin = False
    state = websocket.app.state
    settings = state.settings
    desktop = websocket.headers.get("origin", "") in settings.desktop_origins
    if not same_origin and not desktop:
        await websocket.close(4403, "Origin refused")
        return
    offered = [part.strip() for part in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    subprotocol = BEARER_PROTOCOL if desktop and BEARER_PROTOCOL in offered else None
    token = websocket.cookies.get(settings.session_cookie_name) if not desktop else None
    if subprotocol:
        others = [part for part in offered if part and part != BEARER_PROTOCOL]
        token = others[0] if len(others) == 1 else None
    async with state.database.sessions() as session:
        account = await SessionService(session, settings.session_hours).resolve(token) if token else None
        if account is None:
            await websocket.close(4401, "Not logged in")
            return
        if ((settings.require_email_verification and not account.email_verified)
                or FILES_UPLOAD not in account.permission_names):
            await websocket.close(4403, "Missing upload permission")
            return
    await websocket.accept(subprotocol=subprotocol)
    gateway = ArmoryStreams(state.upstream, state.catalog, state.keyring)
    try:
        async def log_final(byte_count):
            await state.logs.action(account, "attachments.dictate", f"Transcribed {byte_count:,} bytes of dictated audio")

        await gateway.dictate(account, websocket, on_final=log_final)
    except asyncio.CancelledError:
        # The relay drains both directions before cancellation returns here.
        pass
