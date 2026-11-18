"""/api/account-agents: which specialist agents the logged-in account switched off
(any logged-in account; private to it), answered by Stronghold. The account's chat turns leave
those agents out of the roster."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import current_account, get_log_writer, get_stronghold
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.log_service import LogWriter
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/account-agents", tags=["account-agents"])

KEY_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"


@router.get("")
async def read_account_agents(request: Request, account: Account = Depends(current_account),
                              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/account-agents")


@router.put("/{agent_id}")
async def set_account_agent(request: Request, agent_id: str = Path(pattern=KEY_PATTERN),
                            account: Account = Depends(current_account),
                            stronghold: StrongholdForwarder = Depends(get_stronghold),
                            logs: LogWriter = Depends(get_log_writer)) -> Response:
    """Switches one agent on or off; the answer is the whole disabled list as stored."""
    answer = await pass_on(request, stronghold, account, f"/account-agents/{agent_id}")
    if answer.status_code == 200:
        enabled = json.loads(await request.body() or b"{}").get("enabled")
        await logs.action(account, f"account.agent_{'enable' if enabled else 'disable'}",
                          f"{'Enabled' if enabled else 'Disabled'} agent '{agent_id}'")
    return answer
