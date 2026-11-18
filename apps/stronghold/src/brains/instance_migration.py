"""Read the former shared connection for Armory's one-time encrypted import."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.brains.connections import BrainConnections, BrainError, COLLECTION, REVISIONS
from src.citadel_auth import AuthError, current_caller
from src.citadel_auth.brain_migration import seal, verify_acknowledgement

router = APIRouter(prefix="/brains/instance-migration", tags=["brains"])


class Proof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proof: str = Field(max_length=2000, repr=False)


def armory_only():
    service = current_caller()
    if service is None or service.name != "armory":
        raise HTTPException(403, "Armory service required")


@router.post("", dependencies=[Depends(armory_only)])
async def export_instance(body: Proof, request: Request):
    service = BrainConnections(request.app.state.store, request.app.state.box)

    async def load():
        row = await service.current("instance", "")
        if row is None:
            return None
        fields = ("label", "endpoint", "folder", "enabled", "allow_write", "revision", "generation", "updated_at")
        key = service.snapshot(row)["api_key"] if row.get("credential") else None
        return {**{name: row[name] for name in fields}, "api_key": key}

    try:
        return await seal(request.app.state.keyring, body.proof, load)
    except (AuthError, ValueError, TypeError):
        raise HTTPException(403, "Invalid Brain migration proof") from None


@router.post("/ack", status_code=204, dependencies=[Depends(armory_only)])
async def retire_instance(body: Proof, request: Request):
    service = BrainConnections(request.app.state.store, request.app.state.box)
    try:
        revision, generation = await verify_acknowledgement(request.app.state.keyring, body.proof)
    except (AuthError, KeyError, TypeError, ValueError):
        raise HTTPException(403, "Invalid Brain migration proof") from None

    async with request.app.state.brain_migration_lock:
        row = await service.current("instance", "")
        if row is None:
            return Response(status_code=204)
        if (row["revision"], row["generation"]) != (revision, generation):
            raise BrainError("The migration source changed.", 409)

        # Keep the imported version discoverable if retirement stops during revision cleanup.
        await service.store.put(COLLECTION, "instance", row)
        for number in range(1, revision + 1):
            await service.store.delete(REVISIONS, f"instance:{number}")
        await service.store.delete(COLLECTION, "instance")
    return Response(status_code=204)
