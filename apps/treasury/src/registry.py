"""Shared connections and the instances that use them.

A connection is opened once, lazily, no matter how many instances list it. The
registry refcounts it and closes it when the last instance lets go. Because the
cache wraps the connection, instances sharing one also share its cache.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from src.backends.base import DatabaseBackend
from src.config import ConnectionSpec


class UnknownInstance(KeyError):
    pass


class UnknownConnection(KeyError):
    pass


class RawSqlDisabled(PermissionError):
    pass


class ConnectionRegistry:
    def __init__(self, specs: dict[str, ConnectionSpec], build: Callable[[ConnectionSpec], DatabaseBackend]) -> None:
        self._specs = specs
        self._build = build
        self._open: dict[str, DatabaseBackend] = {}
        self._refs: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def spec(self, name: str) -> ConnectionSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise UnknownConnection(name) from None

    def open_names(self) -> list[str]:
        return sorted(self._open)

    async def acquire(self, name: str) -> DatabaseBackend:
        spec = self.spec(name)
        async with self._lock:
            if name not in self._open:
                backend = self._build(spec)
                await backend.connect()
                self._open[name] = backend
            self._refs[name] = self._refs.get(name, 0) + 1
            return self._open[name]

    async def release(self, name: str) -> None:
        async with self._lock:
            self._refs[name] = self._refs.get(name, 0) - 1
            if self._refs[name] <= 0:
                self._refs.pop(name, None)
                backend = self._open.pop(name, None)
                if backend is not None:
                    await backend.close()

    async def close_all(self) -> None:
        async with self._lock:
            backends, self._open, self._refs = list(self._open.values()), {}, {}
        for backend in backends:
            await backend.close()


class Instance:
    """A named handle on a fixed set of connections, acquired on first use."""

    def __init__(self, name: str, connection_names: tuple[str, ...], registry: ConnectionRegistry) -> None:
        self.name = name
        self.connection_names = connection_names
        self._registry = registry
        self._held: dict[str, DatabaseBackend] = {}
        self._lock = asyncio.Lock()

    async def backend(self, connection: str) -> DatabaseBackend:
        if connection not in self.connection_names:
            raise UnknownConnection(f"{connection} (not part of instance {self.name})")
        async with self._lock:
            if connection not in self._held:
                self._held[connection] = await self._registry.acquire(connection)
            return self._held[connection]

    async def sql_backend(self, connection: str) -> DatabaseBackend:
        backend = await self.backend(connection)
        if not self._registry.spec(connection).allow_raw_sql:
            raise RawSqlDisabled(f"raw SQL is disabled for connection {connection}")
        return backend

    async def close(self) -> None:
        async with self._lock:
            held, self._held = list(self._held), {}
        for connection in held:
            await self._registry.release(connection)


class InstanceManager:
    def __init__(self, instances: dict[str, tuple[str, ...]], registry: ConnectionRegistry) -> None:
        self._registry = registry
        self._instances = {name: Instance(name, members, registry) for name, members in instances.items()}

    def get(self, name: str) -> Instance:
        try:
            return self._instances[name]
        except KeyError:
            raise UnknownInstance(name) from None

    def describe(self) -> dict[str, list[str]]:
        return {name: list(inst.connection_names) for name, inst in self._instances.items()}

    async def close(self) -> None:
        for instance in self._instances.values():
            await instance.close()
        await self._registry.close_all()
