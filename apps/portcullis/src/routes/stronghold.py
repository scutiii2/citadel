"""/api/stronghold: routes Portcullis answers by asking Stronghold.

Portcullis checks the login (and, on later routes, the permission) and builds
the Stronghold path itself. This file holds only the proof route; each product
domain adds its own route file and reuses `as_response`.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.deps import current_account, get_stronghold
from src.models import Account
from src.services.stronghold_forwarder import ForwardedResponse, StrongholdForwarder

router = APIRouter(prefix="/api/stronghold", tags=["stronghold"])


def as_response(forwarded: ForwardedResponse) -> Response:
    """Stronghold's status, body and content type, unchanged."""
    headers = {"Retry-After": forwarded.retry_after} if forwarded.retry_after else None
    return Response(forwarded.body, status_code=forwarded.status, media_type=forwarded.content_type, headers=headers)


async def pass_on(request: Request, stronghold: StrongholdForwarder, account: Account, path: str) -> Response:
    """Send this request's method, query and JSON body to a Stronghold path the route built."""
    raw = await request.body()
    try:
        body = json.loads(raw) if raw else None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The body must be JSON") from None
    return as_response(await stronghold.forward(
        request.method, path, account, params=dict(request.query_params), json=body))


@router.get("/whoami")
async def whoami(
    account: Account = Depends(current_account),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    """Who Stronghold sees for this session. Any logged-in account."""
    return as_response(await stronghold.forward("GET", "/whoami", account))
