"""Stronghold's HTTP app. Every route but /health needs the internal token."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, FastAPI

from src.auth import InternalTokenMiddleware
from src.requester import Requester, current_requester


def create_app(token: str) -> FastAPI:
    """token: the shared internal token; "" leaves the app open (tests, loopback)."""
    app = FastAPI(title="stronghold", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(InternalTokenMiddleware, token=token)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    async def whoami(requester: Requester = Depends(current_requester)) -> dict[str, str]:
        """Echoes the identity Portcullis sent. Proves the forwarding path end to end."""
        return asdict(requester)

    return app
