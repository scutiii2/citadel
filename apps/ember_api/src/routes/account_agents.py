"""/api/account-agents: which specialist agents the logged-in account switched off
(any logged-in account; private to it). ember_api leaves those agents out of the
roster of every answer this account asks for."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from src.deps import current_account, get_db_gateway, get_log_writer
from src.models import Account
from src.routes.mcp import get_agent_directory
from src.services.agent_directory import AgentDirectory
from src.services.account_agent_service import AccountAgentService, TooManyItems
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.log_service import LogWriter

router = APIRouter(prefix="/api/account-agents", tags=["account-agents"])

KEY_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"


def get_service(
    account: Account = Depends(current_account), store: DocumentStore = Depends(get_db_gateway)
) -> AccountAgentService:
    return AccountAgentService(store, account.uid)


def _unavailable() -> HTTPException:
    # No fallback to an empty list: that would silently switch every agent back on.
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Account agents storage is unavailable")


class EnabledBody(BaseModel):
    enabled: bool


class AccountAgentsOut(BaseModel):
    disabled: list[str]


@router.get("")
async def read_account_agents(
    service: AccountAgentService = Depends(get_service),
    directory: AgentDirectory = Depends(get_agent_directory),
) -> AccountAgentsOut:
    try:
        return AccountAgentsOut(disabled=await service.disabled(await directory.known_ids()))
    except DbGatewayError as error:
        raise _unavailable() from error


@router.put("/{agent_id}")
async def set_account_agent(
    body: EnabledBody,
    agent_id: str = Path(pattern=KEY_PATTERN),
    account: Account = Depends(current_account),
    service: AccountAgentService = Depends(get_service),
    directory: AgentDirectory = Depends(get_agent_directory),
    logs: LogWriter = Depends(get_log_writer),
) -> AccountAgentsOut:
    """Switches one agent on or off; returns the whole disabled list as stored. Retired agents' ids are dropped."""
    try:
        disabled = await service.set_enabled(agent_id, body.enabled, await directory.known_ids())
    except TooManyItems as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many agents switched off on this account") from error
    except DbGatewayError as error:
        raise _unavailable() from error
    await logs.action(account, f"account.agent_{'enable' if body.enabled else 'disable'}", f"{'Enabled' if body.enabled else 'Disabled'} agent '{agent_id}'")
    return AccountAgentsOut(disabled=disabled)
