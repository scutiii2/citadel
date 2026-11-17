"""/api/admin/treasury: what Treasury holds, read-only, for the Treasury admin app.

Needs settings.manage. Treasury's connections are set in its own config file and each service registers its own instance, so this
only shows them and whether Treasury answers, and which one Portcullis itself uses. Never a credential.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from src.deps import get_db_gateway, get_settings, require_permission
from src.models import Account
from src.services.db_gateway import DbGatewayError
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
