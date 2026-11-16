"""Decision 9: characterize per-request Auth on a real persistent MCP session."""

import asyncio
import socket
import time
import uuid

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.shared._httpx_utils import create_mcp_http_client
from starlette.responses import JSONResponse

from citadel_auth import ServiceAuth
from citadel_auth.testing import make_stack


async def test_persistent_mcp_accepts_per_request_auth_past_assertion_lifetime(tmp_path):
    """Static or session-only authentication would expire before second tool call."""
    stack = await make_stack(tmp_path, services=["legion", "armory"])
    private = stack["legion"].private_key
    seen = []

    class RotatingAuth(httpx.Auth):
        async def async_auth_flow(self, request):
            now = int(time.time())
            request.headers["Authorization"] = "Bearer " + jwt.encode(
                {"iss": "legion", "aud": "armory", "iat": now,
                 "exp": now + 60, "jti": uuid.uuid4().hex}, private, algorithm="EdDSA"
            )
            yield request

    class Verify:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                header = dict(scope["headers"]).get(b"authorization", b"").decode()
                try:
                    claims = jwt.decode(header.removeprefix("Bearer "), private.public_key(),
                                        algorithms=["EdDSA"], audience="armory")
                    assert claims["jti"] not in {item["jti"] for item in seen}
                    seen.append(claims)
                except (jwt.PyJWTError, AssertionError):
                    await JSONResponse({"error": "invalid assertion"}, status_code=401)(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    mcp = FastMCP("auth-spike")

    @mcp.tool()
    async def echo(value: str) -> str:
        return value

    # Bind only within workspace's temporary-port band; retain socket until server owns it.
    listener = socket.socket()
    for port in range(29900, 29999):
        try:
            listener.bind(("127.0.0.1", port))
            break
        except OSError:
            continue
    else:
        listener.close()
        raise RuntimeError("no free temporary port")
    server = uvicorn.Server(uvicorn.Config(Verify(mcp.streamable_http_app()),
        log_level="warning", timeout_graceful_shutdown=2))
    worker = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if worker.done():
                    await worker
                await asyncio.sleep(0.01)
        async with create_mcp_http_client(auth=ServiceAuth(stack["legion"], "armory")) as client:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    first = await session.call_tool("echo", {"value": "before"})
                    assert first.content[0].text == "before"
                    first_expiry = seen[0]["exp"]
                    await asyncio.sleep(61)
                    assert time.time() > first_expiry
                    result = await session.call_tool("echo", {"value": "after"})
                    assert result.content[0].text == "after"
                    assert seen[-1]["iat"] > first_expiry
    finally:
        server.should_exit = True
        await asyncio.wait_for(worker, 10)
        listener.close()
