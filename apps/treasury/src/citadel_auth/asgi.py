"""Plain ASGI authentication with request-scoped identity and policy enforcement."""

import json
import logging
from contextvars import ContextVar

from .errors import AuthError, Forbidden
from .policy import allowed, may_forward
from .requester import _requester, _requester_token, verify_requester
from .tokens import Caller, verify_assertion

_caller: ContextVar[Caller | None] = ContextVar("citadel_caller", default=None)
log = logging.getLogger("citadel_auth")


def current_caller() -> Caller | None:
    return _caller.get()


class ServiceAuthMiddleware:
    """Fail closed for every HTTP route except explicitly public health checks."""

    def __init__(self, app, keyring, audience: str, open_paths=("/health",)):
        self.app, self.keyring, self.audience = app, keyring, audience
        self.open_paths = frozenset(open_paths)
        self._warned = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in self.open_paths:
            await self.app(scope, receive, send)
            return
        try:
            headers = {key.lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
            authorization = headers.get(b"authorization", "")
            if not authorization.startswith("Bearer "):
                raise AuthError("missing service assertion")
            caller = await verify_assertion(self.keyring, authorization[7:], self.audience)
            if not allowed(self.audience, caller.name, scope.get("path", "")):
                raise Forbidden("caller not allowed on route")
            token = headers.get(b"x-citadel-requester", "")
            requester = None
            if token:
                if not may_forward(self.audience, caller.name):
                    raise Forbidden("caller not allowed to forward requester")
                requester = await verify_requester(self.keyring, token, self.audience)
        except AuthError as error:
            if "trust" in str(error) and not self._warned:
                log.warning("Service authentication unavailable: unreadable trust directory")
                self._warned = True
            body = json.dumps({"error": str(error)}).encode()
            await send({"type": "http.response.start", "status": 403 if isinstance(error, Forbidden) else 401,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        caller_context = _caller.set(caller)
        requester_context = _requester.set(requester)
        token_context = _requester_token.set(token)
        scope["citadel_auth"] = (caller, requester, token)
        try:
            await self.app(scope, receive, send)
        finally:
            _requester_token.reset(token_context)
            _requester.reset(requester_context)
            _caller.reset(caller_context)
