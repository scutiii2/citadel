"""/tickets: an account's own tickets, and /ticket-admin: every ticket, for staff. Armory keeps the tickets.

Portcullis serves these as /api/tickets (tickets.create) and /api/admin/tickets and
/api/admin/ticket-groups (tickets.manage) after checking the login and the permission.
The reporter is always the requester; the browser cannot name one, set tags, or pick a source.
Staff changes go to the activity log (ids and field names only, never ticket text).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.clock import utcnow
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.tickets.client import ArmoryTickets
from src.tickets.unread import TicketUnread

router = APIRouter(prefix="/tickets", tags=["tickets"])
admin_router = APIRouter(prefix="/ticket-admin", tags=["tickets-admin"])

TicketType = Literal["bug", "feature", "other"]
TicketStatus = Literal["open", "in_progress", "resolved", "closed"]
TicketPriority = Literal["low", "normal", "high", "urgent"]
TicketId = Annotated[int, Path(ge=1)]


def get_tickets(request: Request) -> ArmoryTickets:
    return request.app.state.tickets


def get_unread(request: Request) -> TicketUnread:
    return request.app.state.ticket_unread


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


def _reporter_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Project explicitly: Armory's staff fields must never reach reporters."""
    fields = ("id", "type", "title", "description", "status", "created_at", "updated_at", "closed_at")
    result = {key: ticket[key] for key in fields if key in ticket}
    if "comments" in ticket:
        comment_fields = ("id", "ticket_id", "author", "author_role", "body", "created_at")
        result["comments"] = [
            {key: comment[key] for key in comment_fields if key in comment}
            for comment in ticket["comments"]
        ]
    return result


def _reporter_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket": _reporter_ticket(result["ticket"]),
        **{key: result[key] for key in ("duplicate", "group_size") if key in result},
    }


def _activity(tickets: list[dict[str, Any]]) -> dict[int, str | None]:
    return {ticket["id"]: ticket.get("last_staff_activity_at") for ticket in tickets}


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: TicketType
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=2000)


# ---- reporter routes -------------------------------------------------------

@router.post("")
async def create_ticket(body: TicketIn, who: Requester = Depends(current_requester),
                        tickets: ArmoryTickets = Depends(get_tickets)) -> JSONResponse:
    payload = {**body.model_dump(), "source": "user", "verified_context": {"via": "portcullis", "account_id": who.uid}}
    result = await tickets.create(who, payload)
    return JSONResponse(_reporter_result(result), status_code=200 if result.get("duplicate") else 201)


@router.get("")
async def list_own_tickets(
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets),
    unread: TicketUnread = Depends(get_unread),
) -> Any:
    result = await tickets.list_own(who, status_filter)
    unread_ids = await unread.unread_ids(who.uid, _activity(result["tickets"]))
    return {"tickets": [{**_reporter_ticket(ticket), "has_unread": ticket["id"] in unread_ids} for ticket in result["tickets"]]}


@router.get("/unread-count")
async def unread_ticket_count(who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets),
                              unread: TicketUnread = Depends(get_unread)) -> Any:
    result = await tickets.list_own(who, None)
    return {"count": len(await unread.unread_ids(who.uid, _activity(result["tickets"])))}


@router.get("/{ticket_id}")
async def get_own_ticket(ticket_id: TicketId, who: Requester = Depends(current_requester),
                         tickets: ArmoryTickets = Depends(get_tickets), unread: TicketUnread = Depends(get_unread)) -> Any:
    fetched_at = utcnow()
    result = await tickets.get_own(who, ticket_id)
    await unread.mark_seen(who.uid, ticket_id, fetched_at)
    projected = _reporter_result(result)
    projected["ticket"]["has_unread"] = ticket_id in await unread.unread_ids(
        who.uid, {ticket_id: result["ticket"].get("last_staff_activity_at")})
    return projected


@router.post("/{ticket_id}/comments")
async def comment_own_ticket(ticket_id: TicketId, body: CommentIn, who: Requester = Depends(current_requester),
                             tickets: ArmoryTickets = Depends(get_tickets)) -> Any:
    return _reporter_result(await tickets.comment_own(who, ticket_id, body.body))


@router.post("/{ticket_id}/close")
async def close_own_ticket(ticket_id: TicketId, who: Requester = Depends(current_requester),
                           tickets: ArmoryTickets = Depends(get_tickets)) -> Any:
    return _reporter_result(await tickets.close_own(who, ticket_id))


@router.post("/{ticket_id}/reopen")
async def reopen_own_ticket(ticket_id: TicketId, who: Requester = Depends(current_requester),
                            tickets: ArmoryTickets = Depends(get_tickets),
                            platform: PortcullisClient = Depends(get_platform)) -> Any:
    result = await tickets.reopen_own(who, ticket_id)
    await platform.log_action(who.uid, "tickets.reopen", f"Reopened ticket {ticket_id}")
    return _reporter_result(result)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        unread: TicketUnread = Depends(get_unread)) -> Response:
    """The read receipts of a deleted account. Portcullis calls it when an administrator deletes the account."""
    await unread.purge_owner(uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- staff routes ----------------------------------------------------------

class TicketPatch(BaseModel):
    """What staff can change on one ticket. An empty assignee clears it."""

    model_config = ConfigDict(extra="forbid")
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assignee: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = Field(default=None, max_length=5)


class MoveIn(BaseModel):
    """Move to an existing group, or split out into a new one with group_id null."""

    model_config = ConfigDict(extra="forbid")
    group_id: Annotated[int, Field(ge=1)] | None


class GroupPatch(BaseModel):
    """Setting a priority pins it; pinned false hands it back to automatic elevation."""

    model_config = ConfigDict(extra="forbid")
    priority: TicketPriority | None = None
    pinned: bool | None = None


@admin_router.get("/tickets")
async def list_all_tickets(
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    type: TicketType | None = None,
    tag: Annotated[str | None, Query(max_length=50)] = None,
    priority: TicketPriority | None = None,
    assignee: Annotated[str | None, Query(max_length=64)] = None,
    group_id: Annotated[int | None, Query(ge=1)] = None,
    possible: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets),
) -> Any:
    filters = {"status": status_filter, "type": type, "tag": tag, "priority": priority, "assignee": assignee,
               "group_id": group_id, "possible": possible, "limit": limit}
    return await tickets.list_all(who, filters)


@admin_router.get("/stats")
async def ticket_stats(who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets)) -> Any:
    return await tickets.stats(who)


@admin_router.get("/settings")
async def ticket_settings(who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets)) -> Any:
    """The ticket settings Armory keeps: tags, elevation rules, Laya limits."""
    return await tickets.settings(who)


@admin_router.patch("/settings")
async def update_ticket_settings(
    changes: dict[str, Any], who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets)
) -> Any:
    """Armory validates the whole document; a refusal comes back as its own message."""
    return await tickets.update_settings(who, changes)


@admin_router.get("/tickets/{ticket_id}")
async def get_any_ticket(ticket_id: TicketId, who: Requester = Depends(current_requester),
                         tickets: ArmoryTickets = Depends(get_tickets)) -> Any:
    return await tickets.get_any(who, ticket_id)


@admin_router.patch("/tickets/{ticket_id}")
async def update_ticket(ticket_id: TicketId, body: TicketPatch, who: Requester = Depends(current_requester),
                        tickets: ArmoryTickets = Depends(get_tickets),
                        platform: PortcullisClient = Depends(get_platform)) -> Any:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nothing to change")
    result = await tickets.update(who, ticket_id, changes)
    await platform.log_action(who.uid, "tickets.update", f"Updated ticket {ticket_id} ({', '.join(sorted(changes))})")
    return result


@admin_router.post("/tickets/{ticket_id}/comments")
async def comment_any_ticket(ticket_id: TicketId, body: CommentIn, who: Requester = Depends(current_requester),
                             tickets: ArmoryTickets = Depends(get_tickets),
                             platform: PortcullisClient = Depends(get_platform)) -> Any:
    result = await tickets.comment_staff(who, ticket_id, body.body)
    await platform.log_action(who.uid, "tickets.comment", f"Commented on ticket {ticket_id}")
    return result


@admin_router.post("/tickets/{ticket_id}/move")
async def move_ticket(ticket_id: TicketId, body: MoveIn, who: Requester = Depends(current_requester),
                      tickets: ArmoryTickets = Depends(get_tickets),
                      platform: PortcullisClient = Depends(get_platform)) -> Any:
    result = await tickets.move(who, ticket_id, body.group_id)
    target = f"group {body.group_id}" if body.group_id else "a new group"
    await platform.log_action(who.uid, "tickets.move", f"Moved ticket {ticket_id} to {target}")
    return result


@admin_router.get("/groups")
async def list_ticket_groups(
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    tag: Annotated[str | None, Query(max_length=50)] = None,
    priority: TicketPriority | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    who: Requester = Depends(current_requester), tickets: ArmoryTickets = Depends(get_tickets),
) -> Any:
    return await tickets.list_groups(who, {"status": status_filter, "tag": tag, "priority": priority, "limit": limit})


@admin_router.patch("/groups/{group_id}")
async def update_ticket_group(group_id: TicketId, body: GroupPatch, who: Requester = Depends(current_requester),
                              tickets: ArmoryTickets = Depends(get_tickets),
                              platform: PortcullisClient = Depends(get_platform)) -> Any:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nothing to change")
    result = await tickets.update_group(who, group_id, changes)
    if "priority" in changes:
        pinned = " (pinned)" if changes.get("pinned", True) else ""
        message = f"Set ticket group {group_id} priority to {changes['priority']}{pinned}"
    else:
        message = f"Changed ticket group {group_id} pin to {'on' if changes['pinned'] else 'off'}"
    await platform.log_action(who.uid, "tickets.group_priority", message)
    return result
