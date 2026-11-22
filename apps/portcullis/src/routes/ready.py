"""Signed dependency readiness and the staff-only stack report."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends, Request

from src.citadel_auth import ServiceAuth, logical_url
from src.citadel_auth.ready import Dependency, PROBE_TIMEOUT
from src.deps import require_permission
from src.services.permissions import SETTINGS_MANAGE


router = APIRouter()
PEERS = ("treasury", "stronghold", "legion", "armory")


@router.get("/ready")
async def ready(request: Request) -> dict:
    state = request.app.state
    return await state.readiness.check([Dependency(name, state.catalog.address(name)) for name in PEERS])


async def _remote(request: Request, name: str) -> dict:
    state = request.app.state
    try:
        async with asyncio.timeout(2 * PROBE_TIMEOUT + 1):
            response = await state.upstream.get(
                logical_url(name) + "/ready",
                auth=ServiceAuth(state.keyring, name),
                timeout=2 * PROBE_TIMEOUT + 1,
            )
        response.raise_for_status()
        report = response.json()
        if isinstance(report, dict) and report.get("service") == name and report.get("status") == "up":
            return report
    except (httpx.HTTPError, TimeoutError, ValueError):
        pass
    return {"service": name, "status": "down"}


@router.get("/api/admin/ready", dependencies=[Depends(require_permission(SETTINGS_MANAGE))])
async def admin_ready(request: Request) -> dict:
    own, *peers = await asyncio.gather(ready(request), *(_remote(request, name) for name in PEERS))
    return {"portcullis": own, **dict(zip(PEERS, peers, strict=True))}
