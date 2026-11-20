"""Register an address in Treasury's outside catalog and keep only ids. Same rules as Legion's runtime/outside_origins.py."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from src.citadel_auth import UnknownService, service_client


class OutsideError(Exception):
    """A refusal the admin can read; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def valid_token(value: str) -> bool:
    """An empty token keeps the existing credential. A new one must fit in an HTTP header."""
    return not value or (value == value.strip() and all(32 <= ord(char) <= 126 for char in value))


class OutsideRegistry:
    def __init__(self, keyring, catalog) -> None:
        self._keyring = keyring
        self._catalog = catalog

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        async with asyncio.timeout(10), service_client(
            self._keyring, "treasury", base_url=self._catalog.url("treasury"), timeout=10.0
        ) as client:
            return await client.post(path, json=body)

    async def _call(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._post(path, body)
        except (httpx.HTTPError, TimeoutError, UnknownService):
            raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502) from None
        if response.status_code >= 500:
            raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502)
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code == 200 and isinstance(data, dict):
            return data
        if response.status_code in (400, 422):
            message = (data.get("detail") or data.get("error")) if isinstance(data, dict) else None
            raise OutsideError(message if isinstance(message, str) else "Treasury refused the address.")
        raise OutsideError(f"Treasury answered HTTP {response.status_code}. Nothing was saved.", 502)

    async def lookup(self, address: str) -> dict[str, Any]:
        return await self._call("/outside/lookup", {"address": address})

    def origin_address(self, origin_id: str) -> str | None:
        try:
            return self._catalog.outside_origin(origin_id)
        except (KeyError, UnknownService):
            return None

    async def entry_from_addresses(self, addresses: list[dict[str, Any]], previous: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(addresses, list) or not addresses or not all(
            isinstance(item, dict) and isinstance(item.get("address"), str) for item in addresses
        ):
            raise OutsideError("addresses must be a list of {address, name?, header_value?}")
        kept = {item.get("origin_id"): item.get("header_value")
                for item in (previous or {}).get("origins", []) if isinstance(item, dict)}
        pending = {}
        service_name = None
        for item in addresses:
            found = await self.lookup(item["address"])
            name = found["group"]["name"] if found["found"] else item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise OutsideError("This address is new: give it a name.")
            name = name.strip().lower()
            if service_name is not None and name != service_name:
                raise OutsideError("All addresses of one connection must belong to the same outside service.")
            address = found["origin"]
            if address in pending:
                raise OutsideError("An address is listed twice.")
            token = item.get("header_value")
            if token is not None and (not isinstance(token, str) or not valid_token(token)):
                raise OutsideError("An address token must be a valid HTTP header value.")
            pending[address] = token
            service_name = name

        service_id = None
        origins = []
        for address, token in pending.items():
            group = await self._call("/outside/origins", {"origin": address, "name": service_name})
            if service_id is not None and group["service_id"] != service_id:
                raise OutsideError("All addresses of one connection must belong to the same outside service.")
            service_id = group["service_id"]
            origin_id = next((item["origin_id"] for item in group["origins"] if item["origin"] == address), None)
            if origin_id is None:
                raise OutsideError("Treasury did not return the registered address. Nothing was saved.", 502)
            origin = {"origin_id": origin_id}
            if token := token or kept.get(origin_id):
                origin["header_value"] = token
            origins.append(origin)
        return {"service_id": service_id, "origins": origins}
