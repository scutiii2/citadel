"""Liveness and readiness through the Treasury API."""

import httpx

from src.api import create_app
from src.backends.factory import build_backend
from src.citadel_auth import ServiceAuth
from src.citadel_auth.testing import make_stack
from src.registry import ConnectionRegistry, InstanceManager


async def test_open_health_and_signed_ready(tmp_path):
    stack = await make_stack(tmp_path)
    manager = InstanceManager({}, ConnectionRegistry({}, build_backend))
    app = create_app(manager, keyring=stack["treasury"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://treasury") as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).status_code == 401
        response = await client.get("/ready", auth=ServiceAuth(stack["portcullis"], "treasury"))
    assert response.status_code == 200
    assert response.json() == {"service": "treasury", "status": "up", "dependencies": []}
