"""POST /holds and /holds/release: Stronghold says which files a chat keeps. Core routes, not tools.

The account is in the body because Stronghold also calls these in the background, where no user request exists; the
access policy lets no other service reach them."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.citadel_auth import current_caller
from src.config import settings
from src.services.chat_holds import ChatHolds, HoldsUnavailable, HoldTarget, StoreAction
from src.services.service_auth import install_auth
from src.services.user_files import runtime as files_runtime

Id = Annotated[str, Field(min_length=1, max_length=64)]


class HoldBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: Id
    chat_id: Id
    file_ids: list[Id] = Field(max_length=500)


class ReleaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: Id
    chat_ids: list[Id] = Field(default_factory=list, max_length=500)
    all: bool = False

    @model_validator(mode="after")
    def one_way(self) -> ReleaseBody:
        if self.all == bool(self.chat_ids):
            raise ValueError("Send chat_ids or all: true.")
        return self


def _shared(action: StoreAction):
    runtime = files_runtime.get_runtime(settings)
    return runtime.call(action(runtime.files.store))


def _media(action: StoreAction):
    # Imported late: the downloader's dependencies may be missing, and then only its store is unavailable.
    from src.capabilities.media_downloader.utils.media_downloads import get_runtime

    return get_runtime().call(lambda service: action(service.store))


def default_holds() -> ChatHolds:
    return ChatHolds((HoldTarget("files", _shared, lambda uid: uid),
                      HoldTarget("media", _media, lambda uid: "uid:" + uid)))


async def _answer(request: Request, model: type[BaseModel], action: Callable[..., dict]) -> JSONResponse:
    caller = current_caller()
    if caller is None:
        return JSONResponse({"error": "Missing authenticated service caller"}, status_code=401)
    if caller.name != "stronghold":
        return JSONResponse({"error": "Only Stronghold keeps chat files"}, status_code=403)
    try:
        body = model.model_validate_json(await request.body())
    except ValidationError:
        return JSONResponse({"error": "Invalid request"}, status_code=422)
    try:
        return JSONResponse(await asyncio.to_thread(action, body))
    except HoldsUnavailable as error:
        return JSONResponse({"error": str(error)}, status_code=503)


def install_holds_routes(app: Starlette, holds: ChatHolds | None = None) -> None:
    holds = holds or default_holds()
    install_auth(app)

    async def hold(request: Request) -> JSONResponse:
        return await _answer(request, HoldBody,
                             lambda body: {"held": holds.hold(body.uid, body.chat_id, body.file_ids)})

    async def release(request: Request) -> JSONResponse:
        return await _answer(request, ReleaseBody, lambda body: {
            "released": holds.release(body.uid, None if body.all else body.chat_ids)})

    app.add_route("/holds", hold, methods=["POST"])
    app.add_route("/holds/release", release, methods=["POST"])
