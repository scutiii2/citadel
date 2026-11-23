"""What every gateway adapter shares: capabilities, the client, and the safe mapping of upstream failures."""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from src.gateway.decision.contract import DecisionRequest, GatewayResult
from src.gateway.decision.errors import GatewayError


async def upstream_post(client: httpx.AsyncClient, url: str, *, json: dict[str, Any], headers: dict[str, str],
                        timeout: float, name: str, method: str = "POST") -> dict[str, Any]:
    """One upstream call. Every failure becomes a GatewayError whose text holds no URL, key or upstream body."""
    try:
        reply = await client.request(method, url, json=json if method == "POST" else None, headers=headers, timeout=timeout)
    except httpx.HTTPError:
        raise GatewayError(502, "gateway_unreachable", f"{name} could not be reached.") from None
    raise_for_status(reply.status_code, name)
    try:
        body = reply.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise GatewayError(502, "gateway_bad_reply", f"{name} sent an unusable reply.")
    return body


def raise_for_status(status: int, name: str) -> None:
    if status < 400:
        return
    if status in (400, 422):
        raise GatewayError(422, "gateway_refused", f"{name} refused the request. Check the images, the question types and the model.")
    if status in (401, 403):
        raise GatewayError(502, "gateway_auth", f"{name} refused the credentials.")
    if status == 413:
        raise GatewayError(413, "too_large", f"{name} says the request is too large.")
    if status in (429, 529):
        raise GatewayError(503, "gateway_busy", f"{name} is busy.", retry_after=1)
    raise GatewayError(502, "gateway_error", f"{name} answered an error.")


class BaseGateway:
    kind = ""
    streams = False
    images = False
    types: frozenset[str] = frozenset({"choice", "score", "noul"})

    def __init__(self, gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.id, self.entry = gateway_id, entry
        self.model = str(entry.get("model", ""))
        self.timeout = float(entry.get("timeout_s", 60))
        # shortcut: the client lives as long as the process and is not closed on shutdown.
        self._client = httpx.AsyncClient(transport=transport, follow_redirects=False)

    async def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        raise NotImplementedError

    async def probe(self) -> str:
        raise NotImplementedError

    async def ask_stream(self, request: DecisionRequest, timeout: float | None = None) -> AsyncIterator[tuple]:
        raise NotImplementedError
        yield  # pragma: no cover
