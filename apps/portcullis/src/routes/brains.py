"""/api/brains: brain settings, browsing, publishing Notes and promotion suggestions.

Stronghold (`apps/stronghold/src/brains`) keeps the encrypted connections and does the work; it asks
Portcullis for the account's permissions on every request. Portcullis checks the login (and chat.use
where it applied) and passes the request on. Armory resolves connections with Stronghold directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.deps import current_account, get_settings, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/brains", tags=["brains"])

require_chat = require_permission(CHAT_USE)


async def valid_account(account: Account = Depends(current_account), settings=Depends(get_settings)) -> Account:
    if settings.require_email_verification and not account.email_verified:
        raise HTTPException(403, "Email not verified")
    return account


@router.get("/connections/{scope}")
async def get_connection(scope: str, request: Request, account: Account = Depends(valid_account),
                         stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/connections/{scope}")


@router.put("/connections/{scope}")
async def save_connection(scope: str, request: Request, account: Account = Depends(valid_account),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/connections/{scope}")


@router.post("/connections/{scope}/test")
async def test_connection(scope: str, request: Request, account: Account = Depends(valid_account),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/connections/{scope}/test")


@router.get("/destinations")
async def destinations(request: Request, account: Account = Depends(valid_account),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/destinations")


@router.post("/browse")
async def browse(request: Request, account: Account = Depends(valid_account),
                 stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/browse")


@router.get("/promotions")
async def list_promotions(request: Request, account: Account = Depends(require_chat),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/promotions")


@router.get("/notes/{note_id}/review")
async def review_publication(note_id: str, request: Request, account: Account = Depends(require_chat),
                             stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/notes/{note_id}/review")


@router.post("/notes/{note_id}/promote")
async def publish_note(note_id: str, request: Request, account: Account = Depends(require_chat),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/notes/{note_id}/promote")


@router.post("/promotions/{promotion_id}/reconcile")
async def reconcile_publication(promotion_id: str, request: Request, account: Account = Depends(require_chat),
                                stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/promotions/{promotion_id}/reconcile")


@router.post("/suggestions/review")
async def review_notes(request: Request, account: Account = Depends(require_chat),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/suggestions/review")


@router.get("/suggestions")
async def list_suggestions(request: Request, account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/suggestions")


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, request: Request, account: Account = Depends(require_chat),
                             stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brains/suggestions/{suggestion_id}/dismiss")
