"""Stronghold trusts only signed service identity and Portcullis requester claims."""
import httpx
import pytest

from src.api import create_app
from src.config import Settings
from src.citadel_auth.testing import make_stack, signed, requester_headers


async def test_signed_requester_and_policy(tmp_path):
    stack = await make_stack(tmp_path)
    app = create_app(keyring=stack["stronghold"], settings=Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stronghold") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/whoami")).status_code == 401
        assert (await client.get("/whoami", headers=signed(stack["legion"], "stronghold"))).status_code == 403
        forged = {**signed(stack["portcullis"], "stronghold"), "X-Requester-Uid": "invented"}
        assert (await client.get("/whoami", headers=forged)).status_code == 400
        headers = {**signed(stack["portcullis"], "stronghold"),
                   **requester_headers(stack["portcullis"], "real", "alice", "a@example.com"),
                   "X-Requester-Uid": "invented"}
        response = await client.get("/whoami", headers=headers)
        assert response.json() == {"uid": "real", "username": "alice", "email": "a@example.com"}
