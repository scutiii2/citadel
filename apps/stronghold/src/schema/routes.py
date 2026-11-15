"""/schema: what Stronghold stores and which schema version the data is at.

For the Stronghold admin app (Plan 7); Portcullis exposes it to administrators only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from src.schema import migrations
from src.schema.catalog import CATALOG

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("")
async def show_schema(request: Request) -> dict[str, Any]:
    state = await migrations.current(request.app.state.store)
    return {
        "version": state["version"], "latest": migrations.latest(), "applied": state["applied"],
        "collections": [{"name": c.name, "domain": c.domain, "key": c.key, "purge": c.purge,
                         "checked": c.model is not None} for c in CATALOG],
    }
