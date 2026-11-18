# apps/portcullis/src/routes/account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits (lower only).

Stronghold (`apps/stronghold/src/tuning`) keeps them and checks them against Legion's own tuning."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from src.deps import current_account, get_stronghold
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/account/tuning", tags=["account-tuning"])


@router.get("")
async def read_limits(request: Request, account: Account = Depends(current_account),
                      stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/tuning/limits")


@router.put("")
async def save_limits(request: Request, account: Account = Depends(current_account),
                      stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/tuning/limits")


@router.delete("", status_code=204)
async def reset_limits(request: Request, account: Account = Depends(current_account),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/tuning/limits")
