"""Admin-only editing and bounded probes for connection transports."""

import asyncio
import json
import re

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.citadel_auth import ServiceAuth
from src.connection_routes import RouteError, read_body, read_json, requester_headers
from src.service_catalog import require_internal_origin
from src.services import extensions, service_auth
from src.services.connections import REQUIRED, ConnectionStore, auth_headers, ready_status

_BODY_LIMIT = 96 * 1024


class ConnectionAdmin:
    def __init__(self, store: ConnectionStore, client: httpx.AsyncClient):
        self.store = store
        self.client = client
        self._mutations = asyncio.Lock()

    def _view(self, record: dict) -> dict:
        view = self.store.view(record)
        if view["mcp"] is not None:
            active = next((status for status in extensions.current_statuses() if status.id == record["name"]), None)
            view["mcp"].update(status=active.status if active else "disconnected",
                               tools=active.tools if active else [], error=active.error if active else None)
        return view

    async def list(self, request: Request) -> JSONResponse:
        records = await asyncio.to_thread(self.store.records)
        return JSONResponse([self._view(record) for record in records.values()])

    async def save(self, request: Request) -> JSONResponse:
        try:
            changes = json.loads(await read_body(request, _BODY_LIMIT))
            if not isinstance(changes, dict):
                raise ValueError("Send a connection object.")
        except (ValueError, UnicodeError):
            return _problem("Send a valid connection object.")
        except RouteError as error:
            return _problem(str(error), error.status)

        creating = request.method == "POST"
        name = request.path_params.get("name", "")
        async with self._mutations:
            records = await asyncio.to_thread(self.store.records)
            if creating:
                label = changes.get("label")
                if not isinstance(label, str) or not label.strip():
                    return _problem("Enter a connection label.")
                if not changes.get("rest") and not changes.get("mcp"):
                    return _problem("Configure an MCP or REST transport.")
                stem = re.sub("[^a-z0-9]+", "_", label.lower()).strip("_")[:48].rstrip("_") or "connection"
                name = stem
                number = 2
                while name in records:
                    name = f"{stem}_{number}"
                    number += 1
            elif name not in records:
                return _problem("Connection not found.", 404)
            try:
                record = await asyncio.to_thread(self.store.update, name, changes)
            except ValueError as error:
                return _problem(str(error))
            previous = records.get(name)
            if (previous is None or any(previous[field] != record[field] for field in
                    ("mcp", "enabled", "label", "description", "web_url"))):
                await extensions.refresh_connection(name, record, self.store.path)
        return JSONResponse(self._view(record), 201 if creating else 200)

    async def remove(self, request: Request) -> Response:
        name = request.path_params["name"]
        if name in REQUIRED:
            return _problem("Required connections cannot be removed.")
        async with self._mutations:
            removed = await asyncio.to_thread(self.store.remove, name)
            if removed:
                await extensions.refresh_connection(name, None, self.store.path)
        return Response(status_code=204) if removed else _problem("Connection not found.", 404)

    async def test(self, request: Request) -> JSONResponse:
        name, transport = request.path_params["name"], request.path_params["transport"]
        records = await asyncio.to_thread(self.store.records)
        record = records.get(name)
        if record is None or transport not in {"mcp", "rest"}:
            return _problem("Connection or transport not found.", 404)
        if not record["enabled"] or not record[transport]:
            return _test(False, "Enable and configure this transport first.")
        if transport == "mcp":
            try:
                config = extensions.config_for_record(record, self.store.path)
                if config.transport != "http":
                    return _test(False, "This local MCP process is managed on the server.")
                tools = await extensions.test_connection(config)
                return _test(True, f"MCP listed {len(tools)} tools.", tools=tools)
            except Exception:
                return _test(False, "MCP did not list tools. Check the address and credentials.")
        return await self._test_rest(record)

    async def _test_rest(self, record: dict) -> JSONResponse:
        state = ready_status(record)
        if not state["ready"]:
            return _test(False, state["reason"])
        rest = record["rest"]
        auth = rest["auth"]
        signed = None
        if auth["kind"] == "internal":
            try:
                require_internal_origin(rest["base_url"], auth["audience"])
            except ValueError as error:
                return _test(False, str(error))
            signed = ServiceAuth(service_auth.keyring, auth["audience"])
        try:
            async with asyncio.timeout(10):
                async with self.client.stream("GET", rest["base_url"] + "/health", headers=auth_headers(auth),
                                              auth=signed, timeout=10, follow_redirects=False) as remote:
                    if remote.status_code in (401, 403):
                        return _test(False, "REST refused the credentials.")
                    if not remote.is_success:
                        return _test(False, f"REST health returned HTTP {remote.status_code}.")
                    body = bytearray()
                    async for chunk in remote.aiter_bytes(chunk_size=4096):
                        if len(body) + len(chunk) > 16384:
                            return _test(False, "REST health response is too large.")
                        body.extend(chunk)
                    try:
                        result = json.loads(body)
                    except (ValueError, UnicodeError):
                        result = None
                    if isinstance(result, dict) and (result.get("ok") is False or result.get("ready") is False):
                        return _test(False, "REST responded but is not ready.")
                if record["name"] in REQUIRED:
                    return await self._test_required_auth(record["name"], rest["base_url"], auth_headers(auth))
                return _test(True, "REST is ready.")
        except RouteError as error:
            return _test(False, str(error))
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            return _test(False, "REST health is unreachable.")

    async def _test_required_auth(self, name: str, origin: str, headers: dict[str, str]) -> JSONResponse:
        """Check an authenticated path without generating or storing any content."""
        headers = {**headers, **requester_headers()}
        method, path, expected, error_code = {
            "bard": ("GET", "/api/voices", 200, None),
            "scribe": ("POST", "/api/transcribe?voice_gate=invalid", 422, "bad_voice_gate"),
            "reader": ("POST", "/api/parse", 422, "invalid_request"),
        }[name]
        async with self.client.stream(method, origin + path, headers=headers,
                                      json={} if name == "reader" else None, follow_redirects=False) as remote:
            if remote.status_code in (401, 403):
                return _test(False, "REST refused the credentials.")
            if remote.status_code == expected and (not error_code or (await read_json(remote)).get("error") == error_code):
                return _test(True, "REST is ready.")
            return _test(False, f"REST health passed, but the authenticated check returned HTTP {remote.status_code}.")


def _problem(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status)


def _test(ok: bool, message: str, **details) -> JSONResponse:
    return JSONResponse({"ok": ok, "message": message, **details})


def install_connection_admin(app: Starlette, store: ConnectionStore, client: httpx.AsyncClient) -> None:
    routes = ConnectionAdmin(store, client)
    path = "/admin/connections"
    app.add_route(path, routes.list, methods=["GET"])
    app.add_route(path, routes.save, methods=["POST"])
    app.add_route(path + "/{name}", routes.save, methods=["PATCH"])
    app.add_route(path + "/{name}", routes.remove, methods=["DELETE"])
    app.add_route(path + "/{name}/test/{transport}", routes.test, methods=["POST"])
