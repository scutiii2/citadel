"""/api/admin/treasury: what Treasury holds, for the Treasury admin app.

Needs settings.manage. GET shows the instances (each service registers its own), whether Treasury answers, and which
one Portcullis itself uses. /connections and /default-cache pass the Connections page on to Treasury, which checks and
keeps them in its settings database. Never a credential: a Postgres dsn is a ${NAME} placeholder, its value is in Treasury's .env.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request

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
