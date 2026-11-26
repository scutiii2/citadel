"""Legion only forwards verified requester tokens, including renewal updates."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from src.citadel_auth import AuthError, Caller, mint_requester
from src.citadel_auth.testing import make_stack, signed
from src.runtime import internal_auth


async def _inbound_policy_and_unsigned_headers(tmp_path):
    stack = await make_stack(tmp_path)
    app = Starlette()
    async def who(request):
        return JSONResponse({"uid": internal_auth.Requester.from_verified().uid})
    app.add_route("/registry", who)
    internal_auth.install_auth(app, stack["legion"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://legion") as client:
        assert (await client.get("/registry")).status_code == 401
        assert (await client.get("/registry", headers=signed(stack["armory"], "legion"))).status_code == 403
        forged = {**signed(stack["stronghold"], "legion"), "X-Requester-Uid": "invented"}
        assert (await client.get("/registry", headers=forged)).json() == {"uid": ""}


async def _running_requester_uses_verified_renewal_without_changing_identity(tmp_path, monkeypatch):
    stack = await make_stack(tmp_path)
    monkeypatch.setattr(internal_auth, "keyring", stack["legion"])
    original = mint_requester(stack["portcullis"], "alice", "alice", "", ["legion", "armory"])
    renewed = mint_requester(stack["portcullis"], "alice", "alice", "", ["legion", "armory"])
    request = SimpleNamespace(scope={"citadel_auth": (Caller("stronghold"), None, "")})

    def context(meta):
        return SimpleNamespace(method="tools/call", request=request, meta=meta)

    async with internal_auth.mcp_requester(context({"requester_token": original})):
        assert internal_auth.requester_meta()["requester_token"] == original
        # A separate status request updates the credential while the original ask context lives.
        async def status_update():
            async with internal_auth.mcp_requester(context({"requester_token": renewed})):
                pass
        await asyncio.create_task(status_update())
        assert internal_auth.current_requester().uid == "alice"
        assert internal_auth.requester_meta()["requester_token"] == renewed
    async with internal_auth.mcp_requester(context({"requester": {"uid": "forged"}})):
        assert not internal_auth.current_requester()
        assert internal_auth.requester_meta() is None
    with pytest.raises(AuthError):
        async with internal_auth.mcp_requester(context({"requester_token": "forged"})):
            pytest.fail("forged requester reached tool")

    async def tool(_context):
        pytest.fail("forged requester reached tool")

    refused = await internal_auth.requester_middleware(context({"requester_token": "forged"}), tool)
    assert refused.is_error


def test_inbound_policy_and_unsigned_headers(tmp_path):
    asyncio.run(_inbound_policy_and_unsigned_headers(tmp_path))


def test_running_requester_uses_verified_renewal_without_changing_identity(tmp_path, monkeypatch):
    asyncio.run(_running_requester_uses_verified_renewal_without_changing_identity(tmp_path, monkeypatch))
