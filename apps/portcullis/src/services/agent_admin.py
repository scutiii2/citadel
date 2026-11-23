"""Edits ai_agent's agent files through ai_agent's own /agents routes.

ai_agent owns the files (agents/<id>.json) and validates every change; its
supervisor then starts, restarts or stops the matching process. This client
only forwards: the browser never names a URL, the route is found in ai_agent's
registry (the entry agent, else any running one), and signed service assertions and
the admin's identity go along like they do for the MCP proxy.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx
from src.citadel_auth import Keyring, ServiceAuth
from src.services import service_auth

from src.models import Account
from src.services.agent_directory import NO_AGENT_RUNNING, AgentDirectory
from src.services.mcp_server_info import base_url
from src.services.traffic import TrafficRecorder

logger = logging.getLogger(__name__)


class AgentAdminUnavailable(Exception):
    """No agent is running, or the one asked did not answer (maps to 502)."""


class AgentAdminRefused(Exception):
    """ai_agent refused the change (4xx); `message` is its own, safe to show."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _without_secret(entry: Any) -> Any:
    """The entry with its token values replaced by `has_value` and `has_override`, so no secret reaches the browser."""
    if not isinstance(entry, dict):
        return entry
    shown = entry
    auth = entry.get("auth")
    if isinstance(auth, dict) and "header_value" in auth:
        kept = {key: value for key, value in auth.items() if key != "header_value"}
        shown = {**shown, "auth": {**kept, "has_value": bool(auth["header_value"])}}
    origins = entry.get("origins")
    if isinstance(origins, list):
        shown = {**shown, "origins": [
            {**{k: v for k, v in item.items() if k != "header_value"}, "has_override": bool(item.get("header_value", item.get("has_override")))}
            if isinstance(item, dict) else item for item in origins]}
    return shown


class AgentAdmin:
    def __init__(
        self,
        client: httpx.AsyncClient,
        directory: AgentDirectory,
        identity: Keyring | None,
        traffic: TrafficRecorder | None = None,
    ) -> None:
        self._client = client
        self._directory = directory
        self._identity = identity or service_auth.keyring
        self._traffic = traffic or TrafficRecorder()

    def _headers(self, account: Account) -> dict[str, str]:
        if account is None:
            return {}
        return service_auth.identity_headers(account.username, account.email, account.uid, identity=self._identity)

    async def _base(self) -> str:
        agent = await self._directory.entry() or next(iter(await self._directory.all()), None)
        if agent is None:
            raise AgentAdminUnavailable(NO_AGENT_RUNNING)
        return base_url(agent.url)

    async def _request(
        self, method: str, path: str, account: Account, json: Any = None, *, timeout: float = 15.0
    ) -> Any:
        base = await self._base()
        try:
            with self._traffic.timed("ai_agent", f"{method} /agents") as timing:
                response = await self._client.request(
                    method, f"{base}{path}", json=json, headers=self._headers(account), auth=ServiceAuth(self._identity, "legion"), timeout=timeout
                )
                timing.ok = response.status_code < 500
        except httpx.HTTPError as error:
            logger.warning("ai_agent %s %s unreachable: %s", method, path, error)
            raise AgentAdminUnavailable(str(error)) from error
        try:
            body = response.json()
        except ValueError:
            body = None
        message = body.get("error") if isinstance(body, dict) else None
        if (
            response.status_code == 502
            and path.startswith("/agents/servers/")
            and message == "[1002] Treasury is unavailable. Nothing was saved."
        ):
            raise AgentAdminRefused(502, message)
        if 400 <= response.status_code < 500:
            raise AgentAdminRefused(response.status_code, str(message or f"ai_agent answered {response.status_code}"))
        if response.status_code >= 500 or body is None:
            raise AgentAdminUnavailable(f"ai_agent answered {response.status_code}")
        return body

    async def gateways(self, account: Account) -> dict[str, Any]:
        body = await self._request("GET", "/agents/gateways", account)
        providers = body.get("providers") if isinstance(body, dict) else None
        return providers if isinstance(providers, dict) else {}

    async def servers(self, account: Account) -> dict[str, Any]:
        """The MCP servers legion connects to, `{id: entry}`. A header value is never returned."""
        body = await self._request("GET", "/agents/servers", account)
        servers = body.get("servers") if isinstance(body, dict) else None
        return {key: _without_secret(value) for key, value in servers.items()} if isinstance(servers, dict) else {}

    async def set_server(self, account: Account, server_id: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Save one server. A header auth sent without its value keeps the value already stored."""
        auth = entry.get("auth")
        if isinstance(auth, dict) and auth.get("type") == "header" and not auth.get("header_value"):
            body = await self._request("GET", "/agents/servers", account)
            stored = (body.get("servers") or {}).get(server_id) if isinstance(body, dict) else None
            old = stored.get("auth") if isinstance(stored, dict) else None
            if isinstance(old, dict) and old.get("header_value"):
                entry = {**entry, "auth": {**auth, "header_value": old["header_value"]}}
        # Legion may look up and register ten addresses, then refresh its catalog.
        timeout = 240.0 if "addresses" in entry else 15.0
        return await self._request("PUT", f"/agents/servers/{quote(server_id, safe='')}", account,
                                   json=entry, timeout=timeout)

    async def lookup_origin(self, account: Account, address: str) -> dict[str, Any]:
        """Legion's answer about an address: whether Treasury's outside catalog knows it, and its group."""
        return await self._request("POST", "/agents/servers/lookup", account, json={"address": address})

    async def model_gateways(self, account: Account, kind: str) -> dict[str, Any]:
        """The saved entries of the built-in gateway (`conversation` or `decision`) with the form and presets."""
        return await self._request("GET", f"/agents/model-gateways/{kind}", account, timeout=30.0)

    async def save_model_gateway(self, account: Account, kind: str, gateway_id: str, entry: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"/agents/model-gateways/{kind}/{quote(gateway_id, safe='')}", account, json=entry)

    async def delete_model_gateway(self, account: Account, kind: str, gateway_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/agents/model-gateways/{kind}/{quote(gateway_id, safe='')}", account)

    async def test_model_gateway(self, account: Account, kind: str, gateway_id: str) -> dict[str, Any]:
        """Does this saved entry answer? {ok, message}; changes nothing."""
        return await self._request("POST", f"/agents/model-gateways/{kind}/{quote(gateway_id, safe='')}/test", account, timeout=30.0)

    async def model_gateway_models(self, account: Account, gateway_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/agents/model-gateways/conversation/{quote(gateway_id, safe='')}/models", account, timeout=30.0)

    async def test_server(self, account: Account, server_id: str) -> dict[str, Any]:
        """Does each address of this MCP server answer? {ok, message, origins}; changes nothing."""
        return await self._request("POST", f"/agents/servers/{quote(server_id, safe='')}/test", account, timeout=30.0)

    async def delete_server(self, account: Account, server_id: str) -> None:
        await self._request("DELETE", f"/agents/servers/{quote(server_id, safe='')}", account)

    async def tuning(self, account: Account) -> dict[str, Any]:
        """legion's editable tuning: {defaults, overrides, effective}."""
        return await self._request("GET", "/agents/tuning", account)

    async def set_tuning(self, account: Account, changes: dict[str, Any]) -> dict[str, Any]:
        """Save `changes` (dotted path -> value, None = back to the file's value); returns the new view."""
        return await self._request("PUT", "/agents/tuning", account, json=changes)

    async def list(self, account: Account) -> list[dict[str, Any]]:
        body = await self._request("GET", "/agents/files", account)
        agents = body.get("agents") if isinstance(body, dict) else None
        return [a for a in agents if isinstance(a, dict)] if isinstance(agents, list) else []

    async def create(self, account: Account, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/agents/files", account, json={"id": agent_id, "config": config})

    async def update(self, account: Account, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"/agents/files/{quote(agent_id, safe='')}", account, json=config)

    async def reset(self, account: Account, agent_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/agents/files/{quote(agent_id, safe='')}/reset", account)

    async def delete(self, account: Account, agent_id: str) -> None:
        await self._request("DELETE", f"/agents/files/{quote(agent_id, safe='')}", account)

    async def prompts(self, account: Account) -> dict[str, Any]:
        body = await self._request("GET", "/agents/prompts", account)
        return body if isinstance(body, dict) else {}

    async def set_prompts(self, account: Account, changes: dict[str, str | None]) -> dict[str, Any]:
        body = await self._request("PUT", "/agents/prompts", account, json=changes)
        return body if isinstance(body, dict) else {}

    async def preview(self, account: Account, agent_id: str, config: dict[str, Any], caveman: bool) -> str:
        body = await self._request(
            "POST", "/agents/prompt-preview", account, json={"id": agent_id, "config": config, "caveman": caveman}
        )
        prompt = body.get("prompt") if isinstance(body, dict) else None
        return prompt if isinstance(prompt, str) else ""
