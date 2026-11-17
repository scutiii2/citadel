"""Portcullis signs service calls and authenticated account identities."""
import threading
import time
from collections import OrderedDict

from src.citadel_auth import Keyring, ServiceAuthMiddleware, from_env, mint_requester

keyring = from_env("portcullis")
_cache: OrderedDict[tuple[str, tuple[str, ...]], tuple[float, str, str, str]] = OrderedDict()
_lock = threading.Lock()
AUDIENCES = ("stronghold", "legion", "armory")


def identity_headers(username: str, email: str, uid: str = "", *, fresh: bool = False,
                     identity: Keyring | None = None) -> dict[str, str]:
    """Cache account assertions for ten minutes; service-level calls carry no user."""
    if not uid:
        return {}
    signing = identity or keyring
    cache_key = (uid, AUDIENCES)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(cache_key)
        if fresh or cached is None or cached[0] <= now or cached[2:] != (username, email):
            token = mint_requester(signing, uid, username, email, list(AUDIENCES))
            cached = (now + 600, token, username, email)
            _cache[cache_key] = cached
        _cache.move_to_end(cache_key)
        while len(_cache) > 50_000:
            _cache.popitem(last=False)
    return {"X-Citadel-Requester": cached[1]}


def tool_headers(username: str, email: str, token: str | None, uid: str = "") -> dict[str, str]:
    """Bard and Scribe sit outside service auth: they keep their own per-caller token."""
    headers = {"X-Requester-Username": username, "X-Requester-Email": email}
    if uid:
        headers["X-Requester-Uid"] = uid
    if token:
        headers["X-Internal-Token"] = token
    return headers


class InternalServiceAuthMiddleware:
    """Protect only internal routes; browser routes keep account/session authentication."""

    def __init__(self, app, identity: Keyring):
        self.app = app
        self.protected = ServiceAuthMiddleware(app, identity, "portcullis")

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/internal" or path.startswith("/internal/")):
            await self.protected(scope, receive, send)
        else:
            await self.app(scope, receive, send)
