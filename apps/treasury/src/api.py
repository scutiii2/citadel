"""HTTP API. Every route but /health requires a signed service assertion.

Records live at /instances/{instance}/connections/{connection}/collections/{collection}/...
A connection is reachable only through an instance that lists it.
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.citadel_auth import Keyring, ServiceAuthMiddleware, current_caller, data_dir, from_env, settings_store
from src.backends.base import UnsupportedOperation
from src import connection_admin
from src.registry import InstanceManager, RawSqlDisabled, UnknownConnection, UnknownInstance

MAX_LIMIT = 1000
BASE = "/instances/{instance}/connections/{connection}"


class PutBody(BaseModel):
    doc: dict[str, Any]


class QueryBody(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(100, ge=1, le=MAX_LIMIT)
    offset: int = Field(0, ge=0)


class SqlBody(BaseModel):
    sql: str
    params: list[Any] = Field(default_factory=list)


def _error(status: int):
    async def handler(request: Request, error: Exception) -> JSONResponse:
        message = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
        return JSONResponse({"error": str(message)}, status_code=status)

    return handler


class InstanceBody(BaseModel):
    connections: list[str]


# An instance a service may register besides the one named like itself.
OWNED_INSTANCES = {"portcullis": {"portcullis", "ember"}, "armory": {"armory", "mcp_server"}}


def create_app(manager: InstanceManager, keyring: Keyring | None = None, settings_db: Path | None = None) -> FastAPI:
    keyring = keyring if keyring is not None else from_env("treasury", data_dir=data_dir(Path(__file__).resolve().parent.parent))
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await keyring.ensure_identity()
        yield
        await manager.close()

    app = FastAPI(title="db_gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(ServiceAuthMiddleware, keyring=keyring, audience="treasury")

    for error, status in (
        (UnknownInstance, 404), (UnknownConnection, 404), (RawSqlDisabled, 403),
        (UnsupportedOperation, 400), (ValueError, 400), (sqlite3.Error, 400),
    ):
        app.add_exception_handler(error, _error(status))

    @app.exception_handler(RequestValidationError)
    async def bad_body(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "invalid request body", "detail": str(error.errors()[:3])}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/instances")
    async def instances() -> dict[str, list[str]]:
        return manager.describe()

    @app.put("/instances/{name}")
    async def register_instance(name: str, body: InstanceBody) -> dict[str, Any]:
        """A service registers its own instance: which connections it uses. Takes effect at once and is kept for the next start."""
        caller = current_caller()
        if caller is None or name not in OWNED_INSTANCES.get(caller.name, {caller.name}):
            raise HTTPException(403, f"{caller.name if caller else 'this caller'} may not register instance {name!r}")
        await manager.register(name, tuple(body.connections))  # unknown connections: 404
        if settings_db is not None:
            settings_store.put(settings_db, "instances", name, list(dict.fromkeys(body.connections)))
        return {"saved": name}

    def _admin_only() -> None:
        """The connections page is Portcullis's (staff only there); no other service may change a connection."""
        caller = current_caller()
        if caller is None or caller.name != "portcullis":
            raise HTTPException(403, "only Portcullis may change connections")
        if settings_db is None:
            raise HTTPException(409, "this Treasury keeps no settings database")

    @app.get("/admin/connections")
    async def list_connections() -> dict[str, Any]:
        _admin_only()
        return connection_admin.view(settings_db, manager)

    @app.put("/admin/connections/{name}")
    async def put_connection(name: str, spec: dict[str, Any]) -> dict[str, Any]:
        _admin_only()
        try:
            applies = connection_admin.save_connection(settings_db, manager, name, spec)
        except connection_admin.ConnectionAdminError as error:
            raise HTTPException(400, str(error)) from error
        return {**connection_admin.view(settings_db, manager), "applies": applies}

    @app.delete("/admin/connections/{name}")
    async def delete_connection(name: str) -> dict[str, Any]:
        _admin_only()
        try:
            applies = connection_admin.remove_connection(settings_db, manager, name)
        except connection_admin.ConnectionAdminError as error:
            raise HTTPException(400, str(error)) from error
        return {**connection_admin.view(settings_db, manager), "applies": applies}

    @app.put("/admin/default-cache")
    async def put_default_cache(changes: dict[str, Any] | None = None) -> dict[str, Any]:
        """Body: ttl_seconds, max_entries and/or negative_ttl_seconds; an empty body puts the built-in defaults back."""
        _admin_only()
        try:
            connection_admin.save_default_cache(settings_db, changes or None)
        except connection_admin.ConnectionAdminError as error:
            raise HTTPException(400, str(error)) from error
        return {**connection_admin.view(settings_db, manager), "applies": "next start"}

    @app.get(BASE + "/collections/{collection}/records/{key}")
    async def get_record(instance: str, connection: str, collection: str, key: str) -> dict[str, Any]:
        backend = await manager.get(instance).backend(connection)
        doc = await backend.get(collection, key)
        if doc is None:
            raise HTTPException(404, f"no record {key!r} in {collection!r}")
        return {"doc": doc}

    @app.put(BASE + "/collections/{collection}/records/{key}")
    async def put_record(
        instance: str, connection: str, collection: str, key: str, body: PutBody, if_absent: bool = False
    ) -> dict[str, Any]:
        backend = await manager.get(instance).backend(connection)
        if if_absent:
            if not await backend.create(collection, key, body.doc):
                raise HTTPException(409, f"record {key!r} already exists in {collection!r}")
        else:
            await backend.put(collection, key, body.doc)
        return {"ok": True}

    @app.delete(BASE + "/collections/{collection}/records/{key}")
    async def delete_record(instance: str, connection: str, collection: str, key: str) -> dict[str, Any]:
        backend = await manager.get(instance).backend(connection)
        if not await backend.delete(collection, key):
            raise HTTPException(404, f"no record {key!r} in {collection!r}")
        return {"ok": True}

    @app.post(BASE + "/collections/{collection}/query")
    async def query(instance: str, connection: str, collection: str, body: QueryBody) -> dict[str, Any]:
        backend = await manager.get(instance).backend(connection)
        return {"docs": await backend.query(collection, body.filters, body.limit, body.offset)}

    @app.post(BASE + "/sql")
    async def sql(instance: str, connection: str, body: SqlBody) -> dict[str, Any]:
        backend = await manager.get(instance).sql_backend(connection)
        return {"rows": await backend.execute_sql(body.sql, body.params)}

    return app
