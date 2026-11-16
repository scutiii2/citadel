"""/account-agents: which specialist agents the account switched off. Portcullis serves it as
/api/account-agents (any login) and reads the list when a chat turn starts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel

from src.agents.accounts import AccountAgentService, TooManyItems, purge_owner
from src.agents.directory import AgentDirectory
from src.document_store import DbGatewayError
from src.requester import Requester, current_requester

router = APIRouter(prefix="/account-agents", tags=["account-agents"])

KEY_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"


def get_service(request: Request, who: Requester = Depends(current_requester)) -> AccountAgentService:
    return AccountAgentService(request.app.state.store, who.uid)


def get_directory(request: Request) -> AgentDirectory:
    return request.app.state.agents


def _unavailable() -> HTTPException:
    # No fallback to an empty list: that would silently switch every agent back on.
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Account agents storage is unavailable")


class EnabledBody(BaseModel):
    enabled: bool


class AccountAgentsOut(BaseModel):
    disabled: list[str]


@router.get("")
async def read_account_agents(service: AccountAgentService = Depends(get_service),
                              directory: AgentDirectory = Depends(get_directory)) -> AccountAgentsOut:
    try:
        return AccountAgentsOut(disabled=await service.disabled(await directory.known_ids()))
    except DbGatewayError as error:
        raise _unavailable() from error


@router.put("/{agent_id}")
async def set_account_agent(body: EnabledBody, agent_id: str = Path(pattern=KEY_PATTERN),
                            service: AccountAgentService = Depends(get_service),
                            directory: AgentDirectory = Depends(get_directory)) -> AccountAgentsOut:
    """Switches one agent on or off; returns the whole disabled list as stored. Retired agents' ids are dropped."""
    try:
        return AccountAgentsOut(disabled=await service.set_enabled(agent_id, body.enabled, await directory.known_ids()))
    except TooManyItems as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many agents switched off on this account") from error
    except DbGatewayError as error:
        raise _unavailable() from error


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")], request: Request) -> Response:
    """A deleted account's switched-off list. Portcullis calls it when an administrator deletes the account."""
    await purge_owner(request.app.state.store, uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
