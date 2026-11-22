"""Tool connection readiness and password-free admin responses through Portcullis."""

import json

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel

from src.deps import current_account, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import TOOL_SERVICES_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable

router = APIRouter(prefix="/api", tags=["connections"])
manage = require_permission(TOOL_SERVICES_MANAGE)
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
