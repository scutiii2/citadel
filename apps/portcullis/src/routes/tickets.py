"""/api/tickets: a signed-in account's own tickets (tickets.create), and
/api/admin/tickets + /api/admin/ticket-groups: every ticket for staff (tickets.manage).

Portcullis checks the login and the permission; Stronghold (`apps/stronghold/src/tickets`) answers.
The reporter is always the logged-in account; the browser cannot name one, set tags, or pick a source.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import TICKETS_CREATE, TICKETS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/tickets", tags=["tickets"])
admin_router = APIRouter(prefix="/api/admin", tags=["tickets-admin"])

require_create = require_permission(TICKETS_CREATE)
require_manage = require_permission(TICKETS_MANAGE)

TicketId = Annotated[int, Path(ge=1)]


# ---- reporter routes -------------------------------------------------------

@router.api_route("", methods=["GET", "POST"])
async def tickets(request: Request, account: Account = Depends(require_create),
                  stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/tickets")


@router.get("/unread-count")
async def unread_ticket_count(request: Request, account: Account = Depends(require_create),
                              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/tickets/unread-count")


@router.get("/{ticket_id}")
async def get_own_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_create),
                         stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/tickets/{ticket_id}")


@router.post("/{ticket_id}/comments")
async def comment_own_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_create),
                             stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/tickets/{ticket_id}/comments")


@router.post("/{ticket_id}/close")
async def close_own_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_create),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/tickets/{ticket_id}/close")


@router.post("/{ticket_id}/reopen")
async def reopen_own_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_create),
                            stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/tickets/{ticket_id}/reopen")


# ---- staff routes ----------------------------------------------------------

@admin_router.get("/tickets")
async def list_all_tickets(request: Request, account: Account = Depends(require_manage),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/ticket-admin/tickets")


@admin_router.get("/tickets/stats")
async def ticket_stats(request: Request, account: Account = Depends(require_manage),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/ticket-admin/stats")


@admin_router.api_route("/ticket-settings", methods=["GET", "PATCH"])
async def ticket_settings(request: Request, account: Account = Depends(require_manage),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    """The ticket settings (tags, elevation, Laya limits) Armory keeps; staff read and change them here."""
    return await pass_on(request, stronghold, account, "/ticket-admin/settings")


@admin_router.api_route("/tickets/{ticket_id}", methods=["GET", "PATCH"])
async def any_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_manage),
                     stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/ticket-admin/tickets/{ticket_id}")


@admin_router.post("/tickets/{ticket_id}/comments")
async def comment_any_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_manage),
                             stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/ticket-admin/tickets/{ticket_id}/comments")


@admin_router.post("/tickets/{ticket_id}/move")
async def move_ticket(ticket_id: TicketId, request: Request, account: Account = Depends(require_manage),
                      stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/ticket-admin/tickets/{ticket_id}/move")


@admin_router.get("/ticket-groups")
async def list_ticket_groups(request: Request, account: Account = Depends(require_manage),
                             stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/ticket-admin/groups")


@admin_router.patch("/ticket-groups/{group_id}")
async def update_ticket_group(group_id: TicketId, request: Request, account: Account = Depends(require_manage),
                              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/ticket-admin/groups/{group_id}")
