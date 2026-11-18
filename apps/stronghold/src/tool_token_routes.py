"""/admin/tool-tokens: the tokens Stronghold presents to Bard, Scribe and Reader. Portcullis serves them to staff
as /api/admin/stronghold-tool-tokens (settings.manage). A token is saved in Stronghold's settings database, used by
the next request, and never returned."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src import tool_tokens

router = APIRouter(prefix="/admin/tool-tokens", tags=["tool-tokens"])


def _current(request: Request) -> dict[str, str | None]:
    return {name: ("set" if getattr(request.app.state, name).has_token else None) for name in tool_tokens.NAMES}


def _path(request: Request):
    return request.app.state.settings.data_dir / "settings.db"


@router.get("")
async def tool_tokens_view(request: Request) -> Any:
    return tool_tokens.view(_path(request), _current(request))


@router.put("")
async def set_tool_tokens(changes: dict[str, str | None], request: Request) -> Any:
    try:
        saved = tool_tokens.update(_path(request), changes)
    except tool_tokens.TokenError as error:
        raise HTTPException(400, str(error)) from error
    for name, token in saved.items():
        # A removed token falls back to the environment's one (the starting value), if any.
        getattr(request.app.state, name).set_token(tool_tokens.token_for(_path(request), name, request.app.state.env_tokens.get(name)))
    return tool_tokens.view(_path(request), _current(request))
