"""/api/calendar: the logged-in account's schedule and alerts, answered by Stronghold.

Portcullis checks the login and the calendar.use permission, then passes the request on
with the account's identity. The calendar itself (feeds, events, alarms, alerts) lives in Stronghold.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CALENDAR_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
require_calendar = require_permission(CALENDAR_USE)

# Lower-case segments only: no dots, so the path cannot climb out of /calendar.
# /accounts is Stronghold's purge route, which only delete_account below may call.
Subpath = Annotated[str, Path(pattern=r"^[a-z0-9-]+(/[a-z0-9-]+)*$")]


@router.api_route("/{subpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def calendar(
    subpath: Subpath,
    request: Request,
    account: Account = Depends(require_calendar),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    if subpath.split("/", 1)[0] == "accounts":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return await pass_on(request, stronghold, account, f"/calendar/{subpath}")
