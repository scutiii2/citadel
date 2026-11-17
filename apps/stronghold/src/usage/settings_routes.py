"""/admin/usage-settings: the usage limits and the price table. Portcullis serves them to staff as
/api/admin/stronghold-usage-settings (settings.manage). A change is saved in Stronghold's settings database and used at once."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.usage import admin_settings

router = APIRouter(prefix="/admin/usage-settings", tags=["usage-settings"])


def _path(request: Request):
    return request.app.state.settings.data_dir / "settings.db"


def _view(request: Request) -> dict[str, Any]:
    return admin_settings.view(request.app.state.settings.usage, request.app.state.pricing, _path(request))


@router.get("")
async def usage_settings(request: Request) -> Any:
    return _view(request)


@router.put("")
async def set_usage_settings(changes: dict[str, Any], request: Request) -> Any:
    try:
        admin_settings.update(request.app.state.settings.usage, request.app.state.pricing, _path(request), changes)
    except admin_settings.UsageSettingsError as error:
        raise HTTPException(400, str(error)) from error
    return _view(request)
