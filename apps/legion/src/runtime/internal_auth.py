"""Legion service identity and verified requester context for shared MCP sessions."""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

import jwt

from pathlib import Path

from src.citadel_auth import data_dir
from src.citadel_auth import (
    AuthError, ServiceAuthMiddleware, current_requester as verified_requester,
    current_requester_token, from_env, requester_context,
)

keyring = from_env("legion", data_dir=data_dir(Path(__file__).resolve().parents[2]))
_latest: OrderedDict[str, tuple[float, str]] = OrderedDict()
_lock = threading.Lock()
_CHAT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True)
class Requester:
    username: str = ""
    email: str = ""
    uid: str = ""
    requester_token: str = field(default="", repr=False)
    chat_id: str = ""

    @classmethod
    def from_verified(cls) -> "Requester":
        who = verified_requester()
        if who is None:
            return cls()
        return cls(who.username, who.email, who.uid, requester_token=current_requester_token())

    def __bool__(self):
        return bool(self.uid or self.username or self.email)


_requester: ContextVar[Requester] = ContextVar("legion_requester", default=Requester())


def bind_requester(requester: Requester) -> Token:
    """Bind an already-verified account for a turn or a pure domain test."""
    return _requester.set(requester)


def reset_requester(token: Token) -> None:
    _requester.reset(token)


def current_requester() -> Requester:
    return _requester.get()


def _remember(uid: str, token: str) -> None:
    expiry = float(jwt.decode(token, options={"verify_signature": False})["exp"])
    with _lock:
        while _latest and next(iter(_latest.values()))[0] <= time.time():
            _latest.popitem(last=False)
        existing = _latest.get(uid)
        if existing is None or expiry >= existing[0]:
            _latest[uid] = (expiry, token)
            _latest.move_to_end(uid)
        while len(_latest) > 50_000:
            _latest.popitem(last=False)


def requester_token() -> str:
    """Every worker sees renewal updates; an expired credential is never forwarded."""
    who = current_requester()
    token = who.requester_token or current_requester_token()
    if who.uid:
        with _lock:
            latest = _latest.get(who.uid)
        if latest is not None:
            expiry, token = latest
    if not token:
        return ""
    try:
        expiry = float(jwt.decode(token, options={"verify_signature": False})["exp"])
        if time.time() >= expiry:
            raise AuthError("requester token expired")
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise AuthError("invalid or expired requester token") from None
    return token


def requester_meta() -> dict | None:
    token = requester_token()
    if not token:
        return None
    meta = {"requester_token": token}
    chat = current_requester().chat_id
    if _CHAT_ID.fullmatch(chat or ""):
        meta["chat_id"] = chat
    return meta


def outbound_headers() -> dict[str, str]:
    token = requester_token()
    return {"X-Citadel-Requester": token} if token else {}


@asynccontextmanager
async def mcp_requester():
    from mcp.server.lowlevel.server import request_ctx
    try:
        context = request_ctx.get()
    except LookupError:
        context = None
    request = getattr(context, "request", None)
    caller, _, header_token = getattr(request, "scope", {}).get("citadel_auth", (None, None, ""))
    meta = getattr(context, "meta", None)
    extras = (meta.model_extra or {}) if meta is not None else {}
    token = extras.get("requester_token", header_token)
    async with requester_context(keyring, caller, token, "legion") as who:
        requester = Requester.from_verified()
        if who is not None:
            _remember(who.uid, token)
            requester = Requester(who.username, who.email, who.uid, requester_token=token)
        handle = bind_requester(requester)
        try:
            yield requester
        finally:
            reset_requester(handle)


def install_mcp(mcp):
    """Wrap all tools, including status, so every call can publish a verified renewal."""
    if getattr(mcp, "_citadel_auth_installed", False):
        return
    async def call(name, arguments):
        async with mcp_requester():
            return await mcp.call_tool(name, arguments)
    mcp._mcp_server.call_tool(validate_input=False)(call)
    mcp._citadel_auth_installed = True


def install_auth(app, identity=None):
    if not getattr(app.state, "citadel_auth_installed", False):
        app.add_middleware(ServiceAuthMiddleware, keyring=identity or keyring, audience="legion")
        app.state.citadel_auth_installed = True
