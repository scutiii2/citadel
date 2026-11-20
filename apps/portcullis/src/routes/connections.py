"""Tool connection readiness and password-free admin responses through Portcullis."""

import json
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel

from src.deps import current_account, get_stronghold, require_permission
from src.models import Account
from src.routes.server_info import _call, get_server_info
from src.routes.stronghold import pass_on
from src.services.mcp_server_info import McpServerInfo
from src.services.permissions import EXTENSIONS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable

router = APIRouter(prefix="/api", tags=["connections"])
manage = require_permission(EXTENSIONS_MANAGE)
REQUIRED = ("bard", "scribe", "reader")


class Readiness(BaseModel):
    ready: bool
    reason: str | None = None


async def readiness(stronghold: StrongholdForwarder, account: Account) -> dict[str, Readiness]:
    """The three fixed status fields from Stronghold; any other text becomes the generic reason."""
    try:
        forwarded = await stronghold.forward("GET", "/tool-services/status", account)
        payload = json.loads(forwarded.body) if forwarded.status == 200 else {}
    except (StrongholdUnavailable, ValueError):
        payload = {}
    result = {}
    for name in REQUIRED:
        status = payload.get(name) if isinstance(payload, dict) else None
        if isinstance(status, dict) and status.get("ready") is True:
            result[name] = Readiness(ready=True)
        else:
            reason = status.get("reason") if isinstance(status, dict) else None
            label = name.title()
            allowed = {f"{label} is disabled in Stronghold Admin.",
                       f"Configure {label} in Stronghold Admin.",
                       f"Set the {label} token in Stronghold Admin."}
            message = reason if isinstance(reason, str) and reason in allowed else "Check Stronghold Admin, Tool services."
            result[name] = Readiness(ready=False, reason=message)
    return result


@router.get("/connection-status")
async def connection_status(account: Account = Depends(current_account),
                            stronghold: StrongholdForwarder = Depends(get_stronghold)) -> dict[str, Readiness]:
    return await readiness(stronghold, account)


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


@router.get("/admin/tool-services")
async def tool_services(request: Request, account: Account = Depends(manage),
                        stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/tool-services")


@router.post("/admin/tool-services/lookup")
async def tool_services_lookup(request: Request, account: Account = Depends(manage),
                               stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/tool-services/lookup")


@router.api_route("/admin/tool-services/{name}", methods=["PUT", "DELETE"])
async def tool_service(request: Request, name: str = Path(pattern=r"^(bard|scribe|reader)$"),
                       account: Account = Depends(manage), stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/admin/tool-services/{name}")


@router.post("/admin/tool-services/{name}/test")
async def tool_service_test(request: Request, name: str = Path(pattern=r"^(bard|scribe|reader)$"),
                            account: Account = Depends(manage), stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/admin/tool-services/{name}/test")
