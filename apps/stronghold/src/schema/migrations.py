"""Versioned changes to stored documents.

Treasury has no migrations of its own, so Stronghold keeps one document (`schema_state`, key
`stronghold`) with the version its documents are at and the steps already run. At start Stronghold runs the
steps above that version, in order, and writes the state after each one. A step must be safe to run twice,
because two replicas may start together or a start may stop halfway. Stronghold refuses to start the
steps when its data is at a NEWER version than this code knows (a rollback), and leaves the data alone.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.clock import utcnow
from src.document_store import DocumentStore
from src.schema.catalog import STATE

logger = logging.getLogger(__name__)
KEY = "stronghold"

Step = Callable[[DocumentStore], Awaitable[None]]


class SchemaTooNew(Exception):
    """The stored data is at a newer version than this Stronghold knows."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    run: Step


async def baseline(_store: DocumentStore) -> None:
    """Version 1 is the documents Plans 5 and 5.2b wrote: nothing to change, only to record."""


# Append new steps; never edit or reorder one that has shipped.
MIGRATIONS: tuple[Migration, ...] = (Migration(1, "baseline", baseline),)


def latest(migrations: tuple[Migration, ...] = MIGRATIONS) -> int:
    return migrations[-1].version if migrations else 0


async def current(store: DocumentStore) -> dict[str, Any]:
    """The stored state: `{"version": n, "applied": [...]}`; version 0 on a fresh database."""
    return await store.get(STATE, KEY) or {"key": KEY, "version": 0, "applied": []}


async def migrate(store: DocumentStore, migrations: tuple[Migration, ...] = MIGRATIONS) -> dict[str, Any]:
    """Runs every step above the stored version and returns the new state."""
    state = await current(store)
    if state["version"] > latest(migrations):
        raise SchemaTooNew(f"data is at schema version {state['version']}, this Stronghold knows {latest(migrations)}")
    for step in migrations:
        if step.version <= state["version"]:
            continue
        await step.run(store)
        state = {**state, "version": step.version,
                 "applied": [*state["applied"], {"version": step.version, "name": step.name, "at": utcnow().isoformat()}]}
        await store.put(STATE, KEY, state)
        logger.info("schema migrated to version %s (%s)", step.version, step.name)
    return state
