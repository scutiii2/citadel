"""Streams one MCP HTTP exchange between the browser and an upstream server.

Only a fixed set of headers crosses in either direction. The browser's own
cookies and any identity/token headers it tries to send are dropped; the
logged-in account's signed identity are
added instead. Responses - including long-lived SSE streams - are relayed
chunk by chunk, and the upstream request is closed as soon as the browser
goes away.
"""

from __future__ import annotations

import logging
import json
from collections.abc import AsyncIterator

import httpx
from src.citadel_auth import Keyring, ServiceAuth
from src.services import service_auth
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.models import Account
from src.services.traffic import TrafficRecorder

logger = logging.getLogger(__name__)

# Lowercase; everything else from the browser is dropped.
_REQUEST_HEADERS = ("content-type", "accept", "mcp-session-id", "mcp-protocol-version", "last-event-id")
_RESPONSE_HEADERS = ("content-type", "mcp-session-id", "cache-control")


class McpProxy:
    def __init__(
        self, client: httpx.AsyncClient, identity: Keyring | None, traffic: TrafficRecorder | None = None
    ) -> None:
        self._client = client
        self._identity = identity or service_auth.keyring
        self._traffic = traffic or TrafficRecorder()

    def _upstream_headers(self, request: Request, account: Account) -> dict[str, str]:
        headers = {name: request.headers[name] for name in _REQUEST_HEADERS if name in request.headers}
        headers.update(service_auth.identity_headers(account.username, account.email, account.uid, identity=self._identity))
        return headers

    async def forward(
        self, request: Request, upstream_url: str, account: Account, body: bytes | None, target: str = "mcp"
    ) -> Response:
        """`target` names the upstream in the traffic counters ("ai_agent" or "mcp_server");
        the timing is up to the response headers, not the end of a stream."""
        headers = self._upstream_headers(request, account)
        if body:
            payload = json.loads(body)
            params = payload.get("params") if isinstance(payload, dict) else None
            if isinstance(params, dict) and payload.get("method") == "tools/call":
                meta = params.get("_meta")
                meta = dict(meta) if isinstance(meta, dict) else {}
                meta.pop("requester", None)
                meta["requester_token"] = headers["X-Citadel-Requester"]
                params["_meta"] = meta
                body = json.dumps(payload).encode()
        upstream_request = self._client.build_request(
            request.method, upstream_url, headers=headers, content=body
        )
        try:
            with self._traffic.timed(target, f"proxy {request.method}") as timing:
                upstream = await self._client.send(upstream_request, stream=True, auth=ServiceAuth(self._identity, "legion" if target == "ai_agent" else "armory"))
                timing.ok = upstream.status_code < 500
        except httpx.HTTPError as error:
            logger.warning("MCP upstream %s unreachable: %s", upstream_url, error)
            return JSONResponse({"detail": "Upstream server unreachable"}, status_code=502)

        async def relay() -> AsyncIterator[bytes]:
            # try/finally rather than a background task: on a browser
            # disconnect the generator is closed, and this still runs.
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()

        headers = {name: upstream.headers[name] for name in _RESPONSE_HEADERS if name in upstream.headers}
        return StreamingResponse(relay(), status_code=upstream.status_code, headers=headers)
