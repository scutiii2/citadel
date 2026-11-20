"""/admin/brain-settings: the brain limits. Portcullis serves them to staff as /api/admin/stronghold-brain-settings
(settings.manage). A change is saved in Stronghold's settings database and used at once."""

from __future__ import annotations

from typing import Any

import sqlite3

from fastapi import APIRouter, Body, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from src.brain import admin_settings
from src.brain.files_routes import BrainRoute

router = APIRouter(prefix="/admin/brain-settings", tags=["brain-settings"], route_class=BrainRoute)


def _path(request: Request):
    return request.app.state.settings.data_dir / "settings.db"


def _view(request: Request) -> dict[str, Any]:
    state = request.app.state
    return admin_settings.view(state.stacks, state.brain_files, state.brain_folder, _path(request),
                               shares=getattr(state, "brain_shares", None))


@router.get("")
async def brain_settings(request: Request) -> Any:
    async with request.app.state.brain_settings_lock:
        try:
            return await run_in_threadpool(_view, request)
        except sqlite3.Error:
            raise HTTPException(503, "Storage is unavailable") from None


@router.put("")
async def set_brain_settings(request: Request, changes: Any = Body()) -> Any:
    state = request.app.state
    async with state.brain_settings_lock:
        try:
            await run_in_threadpool(
                admin_settings.update, state.stacks, state.brain_files, _path(request), changes,
                shares=getattr(state, "brain_shares", None),
                global_files=getattr(getattr(state, "global_brain", None), "files", None),
            )
            return await run_in_threadpool(_view, request)
        except admin_settings.BrainSettingsError as error:
            raise HTTPException(400, str(error)) from None
        except sqlite3.Error:
            raise HTTPException(503, "Storage is unavailable") from None
