"""Saving an MCP connection by address: register each origin in Treasury's outside catalog, keep only ids."""

from __future__ import annotations

from typing import Any

import httpx

from src.citadel_auth import UnknownService, service_client
from src.runtime import internal_auth
from src.runtime.service_catalog import catalog


class OutsideError(Exception):
    """A refusal the admin can read; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


async def _post(path: str, body: dict[str, Any]) -> httpx.Response:
    async with service_client(internal_auth.keyring, "treasury", base_url=catalog.url("treasury"), timeout=10.0) as client:
        return await client.post(path, json=body)


def _text(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error") or "Treasury refused the address.")
    except ValueError:
        return "Treasury refused the address."


async def _call(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await _post(path, body)
    except httpx.HTTPError:
        raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502) from None
    if response.status_code in (502, 503, 504):
        raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502)
    if response.status_code == 200:
        return response.json()
    if response.status_code == 400:
        raise OutsideError(_text(response), 400)
    raise OutsideError(f"[1005] Treasury answered {response.status_code}. Nothing was saved.", 502)


async def lookup(address: str) -> dict[str, Any]:
    return await _call("/outside/lookup", {"address": address})


def origin_address(origin_id: str) -> str | None:
    try:
        return catalog.outside_origin(origin_id)
    except UnknownService:
        return None


async def entry_from_addresses(entry: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve addresses before registering them, then persist only catalog ids and auth."""
    addresses = entry.get("addresses")
    if not isinstance(addresses, list) or not addresses or not all(
            isinstance(item, dict) and isinstance(item.get("address"), str) for item in addresses):
        raise OutsideError("addresses must be a list of {address, name?, header_value?}")
    if entry.get("transport") != "http" or "url" in entry or "command" in entry:
        raise OutsideError("addresses require HTTP transport without a direct URL or command")

    kept = {item.get("origin_id"): item.get("header_value")
            for item in (previous or {}).get("origins", []) if isinstance(item, dict)}
    pending: dict[str, tuple[str, str | None]] = {}
    service_name, path = None, None
    for item in addresses:
        found = await lookup(item["address"])
        name = found["group"]["name"] if found["found"] else item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OutsideError("This address is new: give it a name.")
        name = name.strip().lower()
        address_path = found["path"] or "/mcp"
        if path is not None and address_path != path:
            raise OutsideError("All addresses of one connection must use the same path.")
        if service_name is not None and name != service_name:
            raise OutsideError("All addresses of one connection must belong to the same outside service.")
        address = found["origin"]
        if address in pending:
            raise OutsideError("An address is listed twice.")
        token = item.get("header_value")
        if token is not None and not isinstance(token, str):
            raise OutsideError("An address token must be a string.")
        pending[address] = (name, token)
        service_name, path = name, address_path

    service_id = None
    origins = []
    for address, (name, token) in pending.items():
        group = await _call("/outside/origins", {"origin": address, "name": name})
        if service_id is not None and group["service_id"] != service_id:
            raise OutsideError("All addresses of one connection must belong to the same outside service.")
        service_id = group["service_id"]
        origin_id = next(item["origin_id"] for item in group["origins"] if item["origin"] == address)
        origin = {"origin_id": origin_id}
        if token := token or kept.get(origin_id):
            origin["header_value"] = token
        origins.append(origin)
    stored = {key: value for key, value in entry.items() if key != "addresses"}
    stored.update({"service_id": service_id, "path": path, "origins": origins})
    return stored


def server_view(entry: dict[str, Any]) -> dict[str, Any]:
    """Return connection settings with addresses and token-presence flags."""
    shown = dict(entry)
    auth = entry.get("auth")
    if isinstance(auth, dict) and "header_value" in auth:
        shown["auth"] = {key: value for key, value in auth.items() if key != "header_value"}
        shown["auth"]["has_value"] = bool(auth["header_value"])
    origins = entry.get("origins")
    if isinstance(origins, list):
        shown["origins"] = [
            {"origin_id": ref["origin_id"], "origin": origin_address(ref["origin_id"]),
             "has_override": bool(ref.get("header_value"))}
            for ref in origins if isinstance(ref, dict) and isinstance(ref.get("origin_id"), str)
        ]
    return shown
