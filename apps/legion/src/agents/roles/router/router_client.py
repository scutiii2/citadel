"""Trusted discovery and MCP client for the internal Router, never model-directed."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from src.agents import agent_registry, agent_spec
from src.agents.roles.router.router_contract import RouteRequest, RouteResponse, VoterUsage
from src.runtime import internal_auth
from src.providers import cancellation


def usage_row(row: VoterUsage, request_id: str, delegated_by: str | None = None) -> dict:
    finished = datetime.fromisoformat(row.started_at) + timedelta(milliseconds=row.duration_ms)
    return {"agent_id": "router", "agent_label": "Router", "provider_id": row.provider_id,
        "gateway": "local" if row.provider_id == "laya" else "typesafe",
        "model": row.model, "input_tokens": row.input_tokens, "output_tokens": row.output_tokens,
        "total_tokens": None if row.input_tokens is None else row.input_tokens + (row.output_tokens or 0),
        "started_at": row.started_at, "finished_at": finished.isoformat(),
        "delegated_by": (agent_spec.current().id if delegated_by is None else delegated_by) or None, "request_id": request_id,
        "routing": {"ok": row.ok, "reason": row.reason, "duration_ms": row.duration_ms}}


async def _call(agent: dict, request: RouteRequest) -> dict:
    async with streamablehttp_client(agent["url"], headers=internal_auth.outbound_headers()) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = None
            async with anyio.create_task_group() as tasks:
                async def watch():
                    while True:
                        if cancellation.is_cancelled(request.request_id):
                            await session.call_tool("cancel", {"request_id": request.request_id})
                            tasks.cancel_scope.cancel()
                            return
                        await anyio.sleep(.05)
                tasks.start_soon(watch)
                try:
                    result = await session.call_tool("route", {"request": request.model_dump()})
                finally:
                    tasks.cancel_scope.cancel()
            if result is None or result.isError:
                raise ValueError("Router returned no decision")
            if result.structuredContent is not None:
                return result.structuredContent
            return json.loads(next(c.text for c in result.content if c.type == "text"))


async def decide(request: RouteRequest) -> RouteResponse | None:
    if not internal_auth.TOKEN or cancellation.is_cancelled(request.request_id):
        return None
    try:
        await anyio.to_thread.run_sync(agent_registry.reload)
        routers = [a for a in agent_registry.all_agents() if a.get("role") == "router"]
        if len(routers) != 1:
            return None
        router = routers[0]
        timeout = float(router.get("decision", {}).get("deadline_seconds", 10))
        with anyio.fail_after(min(30, max(1, timeout)) + .5):
            result = RouteResponse.model_validate(await _call(router, request))
        if cancellation.is_cancelled(request.request_id):
            return None
        if result.agent.choice not in {None, "none", *(c.id for c in request.candidates)}:
            return None
        if not set(result.alternatives) <= {c.id for c in request.candidates}:
            return None
        if result.size.choice not in {None, "tiny", "everyday", "large", "hardest"}:
            return None
        return result
    except Exception:
        # Routing availability must never take ordinary chat down; do not log subject/transport secrets.
        return None
