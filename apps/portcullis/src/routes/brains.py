"""/api/brains: brain settings, browsing, publishing Notes and promotion suggestions.

Portcullis proxies personal settings and Brain usage to Stronghold. Shared settings go
to Armory with signed service and requester identity, after checking settings.manage.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.deps import current_account, get_log_writer, get_settings, get_stronghold, require_permission
from src.models import Account
from src.routes.server_info import get_server_info
from src.routes.stronghold import pass_on
from src.services.log_service import LogWriter
from src.services.mcp_server_info import McpServerInfo, McpServerRefused, McpServerUnavailable
from src.services.permissions import CHAT_USE, SETTINGS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/brains", tags=["brains"])

require_chat = require_permission(CHAT_USE)
manage_brain = require_permission(SETTINGS_MANAGE)
admin_router = APIRouter(prefix="/api/admin/brain", tags=["brains"])
_CONNECTION_FIELDS = {"id", "scope", "label", "endpoint", "folder", "enabled", "allow_write",
                      "revision", "generation", "updated_at", "status", "credential_configured"}
_CHECK_FIELDS = {"status", "message", "index_status"}


async def _admin_call(info: McpServerInfo, account: Account, method: str, suffix: str = "", body=None):
    try:
        result = await info.request(method, "/admin/brain" + suffix, account, json=body)
    except McpServerRefused as error:
        raise HTTPException(error.status, str(error)) from None
    except McpServerUnavailable:
        raise HTTPException(502, "Instance Brain is unavailable. Try again shortly.") from None
    if not isinstance(result, dict):
        raise HTTPException(502, "Armory returned an invalid Brain response")
    fields = _CHECK_FIELDS if suffix in {"/test", "/status"} else _CONNECTION_FIELDS
    return {name: value for name, value in result.items() if name in fields}


@admin_router.get("")
async def instance_connection(account: Account = Depends(manage_brain), info: McpServerInfo = Depends(get_server_info)):
    return await _admin_call(info, account, "GET")


@admin_router.put("")
async def save_instance_connection(
    body: dict[str, Any], account: Account = Depends(manage_brain), info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
):
    result = await _admin_call(info, account, "PUT", body=body)
    await logs.action(account, "brain.connection_save", "Saved Instance Brain connection")
    return result


@admin_router.post("/test")
async def test_instance_connection(
    body: dict[str, Any], account: Account = Depends(manage_brain), info: McpServerInfo = Depends(get_server_info),
):
    return await _admin_call(info, account, "POST", "/test", body)


@admin_router.get("/status")
async def instance_status(account: Account = Depends(manage_brain), info: McpServerInfo = Depends(get_server_info)):
    return await _admin_call(info, account, "GET", "/status")


@admin_router.post("/disable")
async def disable_instance_connection(
    body: dict[str, Any], account: Account = Depends(manage_brain), info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
):
    result = await _admin_call(info, account, "POST", "/disable", body)
    await logs.action(account, "brain.connection_save", "Disabled Instance Brain connection")
    return result


async def valid_account(account: Account = Depends(current_account), settings=Depends(get_settings)) -> Account:
    if settings.require_email_verification and not account.email_verified:
        raise HTTPException(403, "Email not verified")
    return account


@router.get("/connections/personal")
async def get_connection(request: Request, account: Account = Depends(valid_account),
                         stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/connections/personal")


@router.put("/connections/personal")
async def save_connection(request: Request, account: Account = Depends(valid_account),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/connections/personal")


@router.post("/connections/personal/test")
async def test_connection(request: Request, account: Account = Depends(valid_account),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brains/connections/personal/test")


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
