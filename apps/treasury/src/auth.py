"""The shared internal token, checked on every route but /health."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from dotenv import dotenv_values

from src.seed import seed_from_example

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
INTERNAL_TOKEN_HEADER = "X-Internal-Token"
OPEN_PATHS = ("/health",)


def load_token(path: Path | None = None) -> str:
    """INTERNAL_API_TOKEN from the environment, else from the project's .env
    (seeded from .env.example on first run). "" = not configured."""
    if path is None:
        path = ENV_PATH
        seed_from_example(path)
    return os.getenv("INTERNAL_API_TOKEN") or dotenv_values(path).get("INTERNAL_API_TOKEN") or ""


class InternalTokenMiddleware:
    """Plain ASGI middleware: a request whose X-Internal-Token does not match
    (constant-time) gets 401 JSON. Does nothing when no token is configured."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self._token = token.encode("utf-8")

    def _protects(self, scope) -> bool:
        return bool(self._token) and scope["type"] == "http" and scope.get("path", "") not in OPEN_PATHS

    async def __call__(self, scope, receive, send):
        if self._protects(scope):
            provided = dict(scope.get("headers") or []).get(INTERNAL_TOKEN_HEADER.lower().encode("latin-1"), b"")
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
