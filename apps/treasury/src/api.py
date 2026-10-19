"""HTTP API. Every route but /health needs X-Internal-Token (once configured).

Records live at /instances/{instance}/connections/{connection}/collections/{collection}/...
A connection is reachable only through an instance that lists it.
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.auth import InternalTokenMiddleware
from src.backends.base import UnsupportedOperation
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


def create_app(manager: InstanceManager, token: str = "") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await manager.close()

    app = FastAPI(title="db_gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(InternalTokenMiddleware, token=token)

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
