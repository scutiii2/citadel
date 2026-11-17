"""Only signed requester identities cross Armory HTTP and MCP boundaries."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from mcp.types import RequestParams
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from src.citadel_auth import AuthError, Caller, mint_requester
from src.citadel_auth.testing import make_stack, signed
from src.services import identity_context, service_auth


@pytest.fixture
async def stack(tmp_path):
    return await make_stack(tmp_path)


async def test_http_only_signed_identity_and_policy(stack):
    async def who(request):
        return JSONResponse({"uid": identity_context.current_uid()})
    app = Starlette()
    app.add_route("/upload", who, methods=["POST"])
    service_auth.install_auth(app, stack["armory"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://armory") as client:
        assert (await client.post("/upload")).status_code == 401
        assert (await client.post("/upload", headers=signed(stack["legion"], "armory"))).status_code == 403
        forged = {**signed(stack["portcullis"], "armory"), "X-Requester-Uid": "invented"}
        assert (await client.post("/upload", headers=forged)).json() == {"uid": ""}
        token = mint_requester(stack["portcullis"], "real", "alice", "", ["armory"])
        headers = {**signed(stack["portcullis"], "armory"), "X-Citadel-Requester": token}
        assert (await client.post("/upload", headers=headers)).json() == {"uid": "real"}
        assert (await client.post("/upload", headers=signed(stack["legion"], "armory"))).status_code == 403


async def test_mcp_signed_meta_and_forged_meta_ignored(stack):
    token = mint_requester(stack["portcullis"], "user-a", "alice", "a@example.com", ["armory"])
    context = RequestContext(request_id=1, meta=RequestParams.Meta(
        requester_token=token, requester={"uid": "forged"}), session=None, lifespan_context=None,
        request=SimpleNamespace(scope={"citadel_auth": (Caller("legion"), None, "")}))
    handle = request_ctx.set(context)
    try:
        async with service_auth.mcp_requester(stack["armory"]):
            assert identity_context.current_uid() == "user-a"
            assert identity_context.current_username() == "alice"
        context.meta = RequestParams.Meta(requester={"uid": "forged", "username": "forged"})
        async with service_auth.mcp_requester(stack["armory"]):
            assert identity_context.current_uid() == ""
            assert identity_context.current_username() == ""
        context.meta = RequestParams.Meta(requester_token="forged")
        with pytest.raises(AuthError):
            async with service_auth.mcp_requester(stack["armory"]):
                pytest.fail("forged requester reached tool")
    finally:
        request_ctx.reset(handle)
    assert identity_context.current_uid() == ""


async def test_real_shared_mcp_session_isolates_signed_requester_per_call(stack, monkeypatch):
    """The actual SDK request context must retain each HTTP request's verified caller."""
    import socket
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.fastmcp import FastMCP
    from src.citadel_auth import ServiceAuth
    from src.services.extensions import ExtensionRegistry

    monkeypatch.setattr(service_auth, "keyring", stack["armory"])
    mcp = FastMCP("requester-isolation")
    @mcp.tool()
    async def whoami() -> str:
        return identity_context.current_uid()
    registry = ExtensionRegistry()
    registry.install(mcp)
    app = mcp.streamable_http_app()
    service_auth.install_auth(app, stack["armory"])
    listener = socket.socket()
    for port in range(29900, 29999):
        try:
            listener.bind(("127.0.0.1", port))
            break
        except OSError:
            continue
    else:
        listener.close()
        raise RuntimeError("no free temporary test port")
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(auth=ServiceAuth(stack["legion"], "armory")) as client:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    for uid in ("alice", "bob", "alice"):
                        token = mint_requester(stack["portcullis"], uid, uid, "", ["armory"])
                        result = await session.call_tool("whoami", {}, meta={"requester_token": token})
                        assert not result.isError and result.content[0].text == uid
                    result = await session.call_tool("whoami", {}, meta={"requester": {"uid": "forged"}})
                    assert not result.isError and result.content[0].text == ""
                    rejected = await session.call_tool("whoami", {}, meta={"requester_token": "forged"})
                    assert rejected.isError
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        listener.close()
