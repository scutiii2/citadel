"""Share links. `router` is for the logged-in account (chat.use): make, list and revoke links.
`public_router` is the one place a chat can be read without logging in: GET /api/shared/{token},
read-only. Stronghold keeps the links; portcullis cuts the chat down to what may be shared
(services/share_service.py), checks the login and the permission, and rate-limits the public read."""

from __future__ import annotations

import html
import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.deps import get_share_limiter, get_stronghold, require_permission
from src.models import Account
from src.routes.chats import ChatId, get_chat_service
from src.routes.stronghold import as_response, pass_on
from src.security import client_ip
from src.services.chat_service import ChatNotFound, ChatService, decode_messages
from src.services.permissions import CHAT_SHARE, CHAT_USE
from src.services.public_rate_limiter import PublicReadLimiter
from src.services.share_service import NothingToShare, snapshot_messages
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api", tags=["shares"])
public_router = APIRouter(prefix="/api/shared", tags=["shares"])

require_chat = require_permission(CHAT_USE)
require_share = require_permission(CHAT_SHARE)

ShareId = Path(ge=1, le=2**31 - 1)
# secrets.token_urlsafe(32) is 43 characters; anything else cannot be a link.
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,64}$")


class CreateShareRequest(BaseModel):
    # Days until the link stops working; null: it never does.
    expires_in_days: Literal[1, 7, 30] | None = 7


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Shared chat not found")


# --- the account's own links --------------------------------------------------------


@router.post("/chats/{chat_id}/shares", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_share)])
async def create_share(
    body: CreateShareRequest,
    request: Request,
    chat_id: str = ChatId,
    account: Account = Depends(require_chat),
    chats: ChatService = Depends(get_chat_service),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Freezes what may be shared of the chat (typed questions and plain
    answers) behind a new link. The response is the only time the link's token
    is shown."""
    try:
        chat = await chats.get(chat_id)
    except ChatNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found") from error
    messages = snapshot_messages(decode_messages(chat))
    if not messages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This chat has nothing to share yet") from NothingToShare(chat_id)
    return as_response(await stronghold.forward(
        "POST", "/shares", account,
        json={"chat_id": chat.chat_id, "title": chat.title, "messages": messages, "expires_in_days": body.expires_in_days}))


@router.get("/shares")
async def list_shares(request: Request, account: Account = Depends(require_chat),
                      stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    """This account's active links (never their tokens), newest first; `chat_id` narrows them to one chat."""
    return await pass_on(request, stronghold, account, "/shares")


@router.delete("/shares/{share_id}")
async def revoke_share(request: Request, share_id: int = ShareId, account: Account = Depends(require_chat),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/shares/{share_id}")


# --- the public read ----------------------------------------------------------------


async def _read(token: str, request: Request, stronghold: StrongholdForwarder, limiter: PublicReadLimiter):
    """The frozen chat behind a link (Stronghold's answer), or the 429 / 404 every public read gives."""
    wait = limiter.retry_after(client_ip(request))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests - wait a moment", headers={"Retry-After": str(wait)}
        )
    if not _TOKEN_PATTERN.fullmatch(token):
        raise _not_found()
    answer = await stronghold.forward("GET", f"/shares/public/{token}", None)
    if answer.status != 200:
        raise _not_found()
    return answer


@public_router.get("/{token}")
async def read_shared_chat(
    token: str,
    request: Request,
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    limiter: PublicReadLimiter = Depends(get_share_limiter),
) -> Response:
    """No login. A link that is unknown, revoked or expired gives the same
    404 as one that never existed. Never cached, never indexed."""
    response = as_response(await _read(token, request, stronghold, limiter))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


# The page a link opens in a browser: `<server>/shared/<token>`. Plain HTML, escaped, no script.
page_router = APIRouter(tags=["shares"])
_PAGE_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{title}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 46rem; padding: 1.5rem 1rem 3rem; }}
h1 {{ font-size: 1.3rem; margin: 0 0 .25rem; }}
.meta {{ opacity: .65; font-size: .85rem; margin-bottom: 1.5rem; }}
.message {{ margin: 0 0 1rem; padding: .75rem 1rem; border-radius: .75rem; border: 1px solid #8884; white-space: pre-wrap; overflow-wrap: anywhere; }}
.user {{ background: #8881; }}
.role {{ display: block; font-size: .75rem; letter-spacing: .05em; text-transform: uppercase; opacity: .65; margin-bottom: .25rem; }}
</style></head><body>
<h1>{title}</h1>
<p class="meta">A shared chat, read only.</p>
{messages}
</body></html>"""


@page_router.get("/shared/{token}", response_class=HTMLResponse)
async def shared_chat_page(
    token: str,
    request: Request,
    stronghold: StrongholdForwarder = Depends(get_stronghold),
    limiter: PublicReadLimiter = Depends(get_share_limiter),
) -> HTMLResponse:
    chat = json.loads((await _read(token, request, stronghold, limiter)).body)
    rows = "\n".join(
        f'<div class="message {"user" if m["role"] == "user" else "assistant"}">'
        f'<span class="role">{"You" if m["role"] == "user" else "Assistant"}</span>{html.escape(m["content"])}</div>'
        for m in chat["messages"]
    )
    page = _PAGE.format(title=html.escape(chat["title"]), messages=rows)
    return HTMLResponse(page, headers={
        "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Content-Security-Policy": _PAGE_CSP})
