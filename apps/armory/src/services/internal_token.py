"""Require the shared internal token (X-Internal-Token) on /mcp, which only trusted servers (chat_app, ai_agent, ember_api) call.
Enforced only when a token is configured, else the loopback-only trust model applies (run.py warns); /upload checks the token itself."""

from __future__ import annotations

import hmac
import json

INTERNAL_TOKEN_HEADER = b"x-internal-token"
PROTECTED_PATH = "/mcp"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_exposed_without_token(host: str, token: str) -> bool:
    """True when the server listens beyond loopback and no internal token is set, so anyone reaching the port can call every tool.
    Any host not in LOOPBACK_HOSTS counts, the safe direction."""
    return not token and host not in LOOPBACK_HOSTS


class InternalTokenMiddleware:
    """Plain ASGI middleware: rejects a /mcp request whose X-Internal-Token doesn't match (constant-time) with 401 JSON.
    Lifespan and other paths pass through."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self._token = token.encode("utf-8")

    def _protects(self, scope) -> bool:
        if not self._token or scope["type"] != "http":
            return False
        path = scope.get("path", "")
        return path == PROTECTED_PATH or path.startswith(PROTECTED_PATH + "/")

    async def __call__(self, scope, receive, send):
        if self._protects(scope):
            provided = dict(scope.get("headers") or []).get(INTERNAL_TOKEN_HEADER, b"")
            if not hmac.compare_digest(self._token, provided):
                body = json.dumps({"error": "Invalid or missing internal API token"}).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
