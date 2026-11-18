"""Tool connection readiness and password-free admin responses through Portcullis."""

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel

from src.deps import current_account, require_permission
from src.models import Account
from src.routes.server_info import _call, get_server_info
from src.services.mcp_server_info import McpServerInfo, McpServerRefused, McpServerUnavailable
from src.services.permissions import EXTENSIONS_MANAGE

router = APIRouter(prefix="/api", tags=["connections"])
manage = require_permission(EXTENSIONS_MANAGE)
REQUIRED = ("bard", "scribe", "reader")


class Readiness(BaseModel):
    ready: bool
    reason: str | None = None


async def readiness(info: McpServerInfo, account: Account) -> dict[str, Readiness]:
    """Expose only the three fixed status fields from Armory."""
    try:
        payload = await info.request("GET", "/connections/status", account)
    except (McpServerUnavailable, McpServerRefused):
        payload = {}
    result = {}
    for name in REQUIRED:
        status = payload.get(name) if isinstance(payload, dict) else None
        if isinstance(status, dict) and status.get("ready") is True:
            result[name] = Readiness(ready=True)
        else:
            allowed_reasons = {f"{name.title()} is disabled in Armory Admin.",
                               f"Configure {name.title()}'s REST connection in Armory Admin.",
                               f"Set the {name.title()} token in Armory Admin."}
            reason = status.get("reason") if isinstance(status, dict) else None
            message = reason if isinstance(reason, str) and reason in allowed_reasons else "Check Armory Admin, Connections."
            result[name] = Readiness(ready=False, reason=message)
    return result


@router.get("/connection-status")
async def connection_status(account: Account = Depends(current_account),
                            info: McpServerInfo = Depends(get_server_info)) -> dict[str, Readiness]:
    return await readiness(info, account)


@router.get("/admin/connections")
async def list_connections(account: Account = Depends(manage), info: McpServerInfo = Depends(get_server_info)):
    return await _call(info.request("GET", "/admin/connections", account))


@router.post("/admin/connections", status_code=201)
async def create_connection(body: dict[str, Any], account: Account = Depends(manage),
                            info: McpServerInfo = Depends(get_server_info)):
    return await _call(info.request("POST", "/admin/connections", account, json=body))


@router.patch("/admin/connections/{name}")
async def update_connection(body: dict[str, Any], name: str = Path(pattern=r"^[a-z0-9_]{1,60}$"),
                            account: Account = Depends(manage), info: McpServerInfo = Depends(get_server_info)):
    return await _call(info.request("PATCH", f"/admin/connections/{quote(name, safe='')}", account, json=body))


@router.delete("/admin/connections/{name}", status_code=204)
async def remove_connection(name: str = Path(pattern=r"^[a-z0-9_]{1,60}$"),
                            account: Account = Depends(manage), info: McpServerInfo = Depends(get_server_info)):
    await _call(info.request("DELETE", f"/admin/connections/{quote(name, safe='')}", account))
    return Response(status_code=204)


@router.post("/admin/connections/{name}/test/{transport}")
async def test_connection(transport: Literal["mcp", "rest"], name: str = Path(pattern=r"^[a-z0-9_]{1,60}$"),
                          account: Account = Depends(manage), info: McpServerInfo = Depends(get_server_info)):
    return await _call(info.request("POST", f"/admin/connections/{quote(name, safe='')}/test/{transport}", account))
