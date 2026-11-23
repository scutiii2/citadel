"""/api/admin/agents: create, edit and remove ai_agent's agent files.

Needs agents.manage. ai_agent validates and stores the files; its supervisor
starts, restarts or stops the agent within a few seconds, so a changed agent
shows as running/offline on GET /api/agents shortly after. Every change is
written to the activity log.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.services.agent_admin import AgentAdmin, AgentAdminRefused, AgentAdminUnavailable
from src.services.log_service import LogWriter
from src.services.permissions import AGENTS_MANAGE

router = APIRouter(prefix="/api/admin/agents", tags=["agent-admin"])
# Not under /api/admin/agents: an agent id such as "prompts" would collide with these paths.
prompts_router = APIRouter(prefix="/api/admin", tags=["agent-admin"])

require_agents_manage = require_permission(AGENTS_MANAGE)

AGENT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"


def get_agent_admin(request: Request) -> AgentAdmin:
    return AgentAdmin(
        request.app.state.upstream, request.app.state.agent_directory,
        request.app.state.keyring, request.app.state.traffic,
    )


async def _call(awaitable) -> Any:
    try:
        return await awaitable
    except AgentAdminUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Legion is unreachable") from error
    except AgentAdminRefused as error:
        code = error.status if error.status in (404, 409, 502) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, str(error)) from error


class CreateAgentIn(BaseModel):
    id: str = Field(pattern=AGENT_ID_PATTERN)
    config: dict[str, Any]


class UpdateAgentIn(BaseModel):
    config: dict[str, Any]


@router.get("/gateways")
async def gateways(account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin)) -> Any:
    """Providers and the gateways each offers, for the pickers."""
    return {"providers": await _call(admin.gateways(account))}


@router.get("")
async def list_agent_files(
    account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin)
) -> Any:
    """Every agent file: `{id, ...the file's fields}`; a broken file carries `error`."""
    return {"agents": await _call(admin.list(account))}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentIn,
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    created = await _call(admin.create(account, body.id, body.config))
    await logs.action(account, "agents.create", f"Created agent '{body.id}'")
    return created


@router.put("/{agent_id}")
async def update_agent(
    body: UpdateAgentIn,
    agent_id: str = Path(pattern=AGENT_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    updated = await _call(admin.update(account, agent_id, body.config))
    await logs.action(account, "agents.update", f"Updated agent '{agent_id}'")
    return updated


@router.post("/{agent_id}/reset")
async def reset_agent(
    agent_id: str = Path(pattern=AGENT_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Drop this machine's edits to an agent so its tracked default file applies again."""
    reset = await _call(admin.reset(account, agent_id))
    await logs.action(account, "agents.reset", f"Reset agent '{agent_id}' to its defaults")
    return reset


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str = Path(pattern=AGENT_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Response:
    await _call(admin.delete(account, agent_id))
    await logs.action(account, "agents.delete", f"Deleted agent '{agent_id}'")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PreviewIn(BaseModel):
    id: str = Field(pattern=AGENT_ID_PATTERN)
    config: dict[str, Any]
    caveman: bool = False


KIND_PATTERN = r"^(conversation|decision)$"
GATEWAY_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,47}$"


@prompts_router.get("/model-gateways/{kind}")
async def list_model_gateways(
    kind: str = Path(pattern=KIND_PATTERN),
    account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin),
) -> Any:
    """The saved entries of the chat or decision gateway, with the form and presets for the page."""
    return await _call(admin.model_gateways(account, kind))


@prompts_router.put("/model-gateways/{kind}/{gateway_id}")
async def save_model_gateway(
    entry: dict[str, Any],
    kind: str = Path(pattern=KIND_PATTERN),
    gateway_id: str = Path(pattern=GATEWAY_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """legion validates and stores the entry. The log names the entry, never its secrets."""
    result = await _call(admin.save_model_gateway(account, kind, gateway_id, entry))
    await logs.action(account, "agents.model_gateway", f"Saved {kind} gateway {gateway_id}")
    return result


@prompts_router.delete("/model-gateways/{kind}/{gateway_id}")
async def delete_model_gateway(
    kind: str = Path(pattern=KIND_PATTERN),
    gateway_id: str = Path(pattern=GATEWAY_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    result = await _call(admin.delete_model_gateway(account, kind, gateway_id))
    await logs.action(account, "agents.model_gateway", f"Deleted {kind} gateway {gateway_id}")
    return result


@prompts_router.post("/model-gateways/{kind}/{gateway_id}/test")
async def test_model_gateway(
    request: Request,
    kind: str = Path(pattern=KIND_PATTERN),
    gateway_id: str = Path(pattern=GATEWAY_ID_PATTERN),
    account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin),
) -> Any:
    """Whether this gateway answers: `{ok, message}`. A body is the unsaved form, tested as filled in."""
    try:  # the body is optional: the table's Test sends none, the drawer's sends the form
        entry = await request.json() if await request.body() else None
    except ValueError:
        entry = None
    return await _call(admin.test_model_gateway(account, kind, gateway_id, entry if isinstance(entry, dict) and entry else None))


@prompts_router.get("/model-gateways/conversation/{gateway_id}/models")
async def model_gateway_models(
    gateway_id: str = Path(pattern=GATEWAY_ID_PATTERN),
    account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin),
) -> Any:
    """The model names the saved chat gateway offers: `{ok, models}`."""
    return await _call(admin.model_gateway_models(account, gateway_id))


SERVER_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,62}$"


class ServerAuthIn(BaseModel):
    model_config = {"extra": "forbid"}

    type: str = Field(max_length=20)
    env_var: str | None = Field(default=None, max_length=200)
    header_name: str | None = Field(default=None, max_length=200)
    header_value: str | None = Field(default=None, max_length=2000, repr=False)


class ServerAddressIn(BaseModel):
    model_config = {"extra": "forbid"}

    address: str = Field(max_length=500)
    name: str | None = Field(default=None, max_length=40)
    header_value: str | None = Field(default=None, max_length=2000, repr=False)


class LookupIn(BaseModel):
    model_config = {"extra": "forbid"}

    address: str = Field(max_length=500)


class ServerIn(BaseModel):
    """One MCP server legion connects to as a client; legion validates the combination."""

    model_config = {"extra": "forbid"}

    label: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    transport: str = Field(max_length=10)
    url: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=500)
    args: list[str] | None = Field(default=None, max_length=50)
    auth: ServerAuthIn | None = None
    path: str | None = Field(default=None, max_length=200)
    addresses: list[ServerAddressIn] | None = Field(default=None, max_length=10)


@prompts_router.get("/servers")
async def list_servers(account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin)) -> Any:
    """The MCP servers legion connects to: `{servers: {id: entry}}`. No header value is returned."""
    return {"servers": await _call(admin.servers(account))}


@prompts_router.post("/servers/lookup")
async def lookup_server_address(
    body: LookupIn, account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin),
) -> Any:
    """Is this address in Treasury's outside catalog? Legion asks; nothing is saved."""
    return await _call(admin.lookup_origin(account, body.address))


@prompts_router.post("/servers/{server_id}/test")
async def test_server(
    server_id: str = Path(pattern=SERVER_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
) -> Any:
    """Whether each address of this MCP server answers: `{ok, message, origins}`."""
    return await _call(admin.test_server(account, server_id))


@prompts_router.put("/servers/{server_id}")
async def put_server(
    body: ServerIn,
    server_id: str = Path(pattern=SERVER_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Add or change a server; legion checks it and applies it at its next start."""
    result = await _call(admin.set_server(account, server_id, body.model_dump(exclude_none=True)))
    await logs.action(account, "agents.server", f"Saved MCP server '{server_id}'")
    return result


@prompts_router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str = Path(pattern=SERVER_ID_PATTERN),
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    await _call(admin.delete_server(account, server_id))
    await logs.action(account, "agents.server", f"Removed MCP server '{server_id}'")
    return {"deleted": server_id}


@prompts_router.get("/agent-prompts")
async def get_prompts(account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin)) -> Any:
    """The prompt texts every agent shares: `{values, defaults, overridden}`."""
    return await _call(admin.prompts(account))


@prompts_router.put("/agent-prompts")
async def set_prompts(
    changes: dict[str, str | None],
    account: Account = Depends(require_agents_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Body `{name: text | null}`; null or blank resets a text. ai_agent restarts every agent to apply it."""
    result = await _call(admin.set_prompts(account, changes))
    await logs.action(account, "agents.prompts", f"Changed shared agent prompts ({', '.join(sorted(changes)) or 'none'})")
    return result


@prompts_router.post("/agent-prompt-preview")
async def preview_prompt(
    body: PreviewIn, account: Account = Depends(require_agents_manage), admin: AgentAdmin = Depends(get_agent_admin)
) -> Any:
    """The system prompt a draft agent file would get: `{prompt}`."""
    return {"prompt": await _call(admin.preview(account, body.id, body.config, body.caveman))}
