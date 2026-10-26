"""Exercise the actual internal MCP handshake, typed result and identity headers."""
import asyncio
import threading
import time
from types import SimpleNamespace

import uvicorn
from mcp.server.fastmcp import Context, FastMCP

from src.agents import agent_spec
from src.agents.roles.router import router_client, router_service
from src.agents.roles.router.router_contract import RouteRequest, RouteResponse, RouterPolicy
from src.runtime import internal_auth
from tests.test_private_integration import free_port


def test_real_mcp_route_roundtrip_has_token_and_structured_response(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "internal-test")
    monkeypatch.setattr(agent_spec, "current", lambda: SimpleNamespace(internal_role="router", decision=RouterPolicy()))
    class Engine:
        def route(self, request, policy, **kwargs):
            return RouteResponse(policy_revision=policy.revision())
    monkeypatch.setattr(router_service, "_engine", Engine())
    port = free_port()
    mcp = FastMCP("router-transport-test", port=port)
    seen = []

    @mcp.tool()
    async def route(request: dict, ctx: Context) -> dict:
        headers = ctx.request_context.request.headers
        seen.append(headers.get("X-Requester-Uid"))
        return await router_service.route(request, headers)

    server = uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1", port=port,
        log_level="warning", timeout_graceful_shutdown=1))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started
    token = internal_auth.bind_requester(internal_auth.Requester(uid="account-uid"))
    try:
        result = asyncio.run(asyncio.wait_for(router_client._call(
            {"url": f"http://127.0.0.1:{port}/mcp"}, RouteRequest(subject="hello", request_id="transport")), 10))
        assert RouteResponse.model_validate(result).agent.uncertain
        assert seen == ["account-uid"]
    finally:
        internal_auth.reset_requester(token)
        server.should_exit = True
        worker.join(10)
