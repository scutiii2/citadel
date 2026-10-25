"""Audio for Bard's text-to-speech results; Bard owns every file."""
from __future__ import annotations

import hmac
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from src.deps import get_db_session, require_permission
from src.models import Account
from src.services.bard import BardGateway
from src.services.permissions import BARD_ADMIN

router = APIRouter(prefix="/api/bard", tags=["bard"])
ID = r"^[0-9a-f]{32}$"


class AdminCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=150)
    # An allowlist, so the internal endpoint cannot be used to probe other permissions.
    permission: Literal["bard.admin", "bard.delete"] = BARD_ADMIN


def gateway(request: Request) -> BardGateway:
    return BardGateway(request.app.state.upstream, request.app.state.settings.bard_url, request.app.state.internal_token)


@router.get("/audio/{file_id}")
async def audio(
    request: Request,
    file_id: str = Path(pattern=ID),
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
    client: BardGateway = Depends(gateway),
):
    return await client.stream(file_id, account, range_header=request.headers.get("range"))


@router.post("/internal/admin-check")
async def admin_check(body: AdminCheck, request: Request, session=Depends(get_db_session)) -> dict[str, bool]:
    """Bard asks whether a username holds bard.admin (or the named bard permission); the answer key stays
    `admin`. Internal token only, so no browser can probe usernames; an unknown, disabled or unverified
    account answers exactly like one without the permission."""
    token = request.app.state.internal_token
    if not token or not hmac.compare_digest(token, request.headers.get("X-Internal-Token", "")):
        raise HTTPException(401, "Valid internal authentication required")
    account = await session.scalar(select(Account).where(Account.username == body.username))
    return {"admin": account is not None and account.is_active and body.permission in account.permission_names}
