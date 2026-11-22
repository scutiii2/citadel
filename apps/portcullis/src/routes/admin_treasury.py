"""/api/admin/treasury: what Treasury holds, for the Treasury admin app.

Needs settings.manage. GET shows the instances (each service registers its own), whether Treasury answers, and which
one Portcullis itself uses. /connections and /default-cache pass the Connections page on to Treasury, which checks and
keeps them in its settings database. Never a credential: a Postgres dsn is a ${NAME} placeholder, its value is in Treasury's .env.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel

from src.deps import get_db_gateway, get_log_writer, get_settings, require_permission
from src.models import Account
from src.services.db_gateway import DbGatewayError, DbGatewayRefused
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE

router = APIRouter(prefix="/api/admin/treasury", tags=["treasury"])


@router.get("")
async def treasury(
    request: Request,
    _account: Account = Depends(require_permission(SETTINGS_MANAGE)),
    store: Any = Depends(get_db_gateway),
    settings: Any = Depends(get_settings),
) -> dict[str, Any]:
    """`reachable` is false (and `instances` empty) when Treasury does not answer, so the page can say so."""
    try:
        instances = await store.instances()
    except DbGatewayError:
        instances = {}
    return {
        "reachable": bool(instances),
        "instances": [{"name": name, "connections": connections} for name, connections in sorted(instances.items())],
        "portcullis": {"instance": settings.db_gateway.instance, "connection": settings.db_gateway.connection},
    }


require_manage = require_permission(SETTINGS_MANAGE)


async def _admin(store: Any, method: str, path: str, body: Any = None) -> Any:
    try:
        return await store.admin(method, path, body)
    except DbGatewayRefused as error:
        raise HTTPException(400, str(error)) from error
    except DbGatewayError as error:
        raise HTTPException(502, "Treasury is unreachable") from error


@router.get("/connections")
async def connections(_account: Account = Depends(require_manage), store: Any = Depends(get_db_gateway)) -> Any:
    """The built-in and saved connections, who uses each, and the cache defaults."""
    return await _admin(store, "GET", "/admin/connections")


@router.put("/connections/{name}")
async def put_connection(
    name: str, spec: dict[str, Any], account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Save one connection. Treasury offers a new one to its instances at once; a changed one is used from its next start."""
    result = await _admin(store, "PUT", f"/admin/connections/{quote(name, safe='')}", spec)
    await logs.action(account, "treasury.connection", f"Saved Treasury connection '{name}'")
    return result


@router.delete("/connections/{name}")
async def delete_connection(
    name: str, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Remove a saved connection (a built-in one comes back); refused while an instance uses a saved one."""
    result = await _admin(store, "DELETE", f"/admin/connections/{quote(name, safe='')}")
    await logs.action(account, "treasury.connection", f"Removed Treasury connection '{name}'")
    return result


@router.put("/default-cache")
async def put_default_cache(
    changes: dict[str, float] | None = None, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Body ttl_seconds, max_entries and/or negative_ttl_seconds; no body puts the built-in defaults back."""
    result = await _admin(store, "PUT", "/admin/default-cache", changes or None)
    await logs.action(account, "treasury.cache", "Changed Treasury cache defaults")
    return result


@router.get("/services")
async def services(_account: Account = Depends(require_manage), store: Any = Depends(get_db_gateway)) -> Any:
    """The effective service addresses and their registered or pinned sources."""
    return await _admin(store, "GET", "/admin/services")


@router.put("/services/{name}")
async def put_service(
    name: str, spec: dict[str, str], account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Pin an address; log the service name without its address."""
    result = await _admin(store, "PUT", f"/admin/services/{quote(name, safe='')}", spec)
    await logs.action(account, "treasury.service_pin", f"Pinned Treasury service '{name}'")
    return result


@router.delete("/services/{name}")
async def delete_service(
    name: str, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Use the service's registered address again."""
    result = await _admin(store, "DELETE", f"/admin/services/{quote(name, safe='')}")
    await logs.action(account, "treasury.service_unpin", f"Unpinned Treasury service '{name}'")
    return result


OutsideId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


class OutsideRename(BaseModel):
    name: str


@router.get("/outside")
async def outside(_account: Account = Depends(require_manage), store: Any = Depends(get_db_gateway)) -> Any:
    """The outside service groups, their origins and which Citadel services use each."""
    return await _admin(store, "GET", "/admin/outside")


@router.patch("/outside/{service_id}")
async def rename_outside(
    service_id: OutsideId, spec: OutsideRename, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Rename a group; its id, and so every consumer's reference, stays the same."""
    result = await _admin(store, "PATCH", f"/admin/outside/{service_id}", {"name": spec.name})
    await logs.action(account, "treasury.outside_rename", f"Renamed outside service '{service_id}'")
    return result


@router.delete("/outside/origins/{origin_id}")
async def delete_outside_origin(
    origin_id: OutsideId, confirm: bool = False, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Remove one origin. Treasury refuses (400) while a service uses the group, unless confirm=true."""
    suffix = "?confirm=true" if confirm else ""
    result = await _admin(store, "DELETE", f"/admin/outside/origins/{origin_id}{suffix}")
    await logs.action(account, "treasury.outside_origin_delete", f"Removed outside origin '{origin_id}'")
    return result


@router.delete("/outside/{service_id}")
async def delete_outside_group(
    service_id: OutsideId, confirm: bool = False, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Remove a group with its origins. Treasury refuses (400) while a service uses it, unless confirm=true."""
    suffix = "?confirm=true" if confirm else ""
    result = await _admin(store, "DELETE", f"/admin/outside/{service_id}{suffix}")
    await logs.action(account, "treasury.outside_delete", f"Removed outside service '{service_id}'")
    return result
