"""HTTP routes for Ascension: thin adapters over the services.

Ownership comes from a verified bearer session only. Request bodies reject
unknown fields, so a client can never supply rewards, stats, chances, random
results or personalities. Every mutation needs an Idempotency-Key header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt

from src.auth import requester
from src.ascension.catalog import SPRITE_NAMES, Catalog, CatalogError
from src.ascension.collection import CollectionService
from src.ascension.coordinator import RoundCoordinator
from src.ascension.encounters import EncounterService
from src.ascension.errors import EncounterCooldown, InvalidRequest, AscendedError
from src.ascension.shop import ShopService
from src.ascension.upgrades import UpgradeService


@dataclass(frozen=True)
class AscendedServices:
    catalog: Catalog
    collection: CollectionService
    encounters: EncounterService
    shop: ShopService
    upgrades: UpgradeService
    coordinator: RoundCoordinator


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InitializeBody(_Body):
    starter_ascended_id: str


class ResetBody(_Body):
    confirm: StrictBool


class PresetBody(_Body):
    instance_ids: list[str]


class StartBody(_Body):
    encounter_id: str
    ascended_id: str
    preset_slot: StrictInt | None = None
    mode: str = "manual"
    emblem_limit: str | None = None


class ActionBody(_Body):
    kind: str
    ability_id: str | None = None
    emblem_tier: str | None = None


class RoundBody(_Body):
    round: StrictInt
    revision: StrictInt


class ActionRequest(RoundBody):
    action: ActionBody


class EmblemRequest(RoundBody):
    tier: str


class ModeRequest(RoundBody):
    mode: str
    emblem_limit: str | None = None


class PurchaseBody(_Body):
    kind: str
    tier: str | None = None
    quantity: StrictInt = 1
    rotation: StrictInt | None = None
    slot: StrictInt | None = None


def idempotency_key(idempotency_key: str = Header(default="", alias="Idempotency-Key")) -> str:
    if not idempotency_key.strip():
        raise HTTPException(400, "an Idempotency-Key header is required for this request")
    return idempotency_key.strip()


def _art_summary(spec: Any) -> dict[str, Any]:
    """The sprite URLs an Ascended has (null for a missing one) and its crop centres."""
    art = spec.art
    present = (art.main_card, art.preview_card, art.battle)
    urls = [f"/ascended/{spec.id}/{name}" if here else None for name, here in zip(SPRITE_NAMES, present)]
    return {"main_card": urls[0], "preview_card": urls[1], "battle": urls[2], "focus": art.focus, "focus_preview": art.focus_preview}


def catalog_summary(catalog: Catalog) -> dict[str, Any]:
    """Public catalog data: Ascended, abilities, tiers, personalities and shop metadata."""
    return {
        "version": catalog.version,
        "tiers": [
            {"id": t.id, "stat_multiplier": t.stat_multiplier, "stars_to_advance": t.stars_to_advance, "essence_cost": t.essence_cost,
             "copy_reward": t.copy_reward,
             "emblem_strength": t.emblem_strength, "emblem_price": t.emblem_price}
            for t in catalog.tiers
        ],
        "levels": {"regular_cap": catalog.levels.regular_cap, "forbidden_cap": catalog.levels.forbidden_cap},
        "ascendeds": [
            {"id": s.id, "name": s.name, "starter": s.starter, "forbidden": s.forbidden, "start_tier": catalog.start_tier(s.id), "ascension_types": [t.value for t in s.ascension_types], "base": dict(s.base),
             "growth": dict(s.growth), "base_price": s.base_price, "passive": s.passive.to_dict(),
             "abilities": [a.to_dict() for a in s.abilities], "art": _art_summary(s)}
            for s in catalog.all_ascendeds()
        ],
        "personalities": [{"id": p.id, "categories": list(p.categories)} for p in catalog.personalities.values()],
    }


def build_router(services: AscendedServices) -> APIRouter:
    router = APIRouter(prefix="/ascension", dependencies=[Depends(requester)])
    collection, encounters, shop, coordinator = services.collection, services.encounters, services.shop, services.coordinator

    @router.get("/catalog")
    async def catalog() -> dict[str, Any]:
        return catalog_summary(services.catalog)

    @router.post("/profile", status_code=201)
    async def create_profile(body: InitializeBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await collection.initialize(owner, key, body.starter_ascended_id)

    @router.post("/profile/reset")
    async def reset_profile(body: ResetBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        if not body.confirm:
            raise InvalidRequest("send confirm: true to reset all progress")
        return await collection.reset(owner, key)

    @router.get("/profile")
    async def get_profile(owner: str = Depends(requester)):
        return await collection.profile(owner)

    @router.get("/ascendeds/{ascended_id}/personalities")
    async def list_personalities(ascended_id: str, limit: int | None = Query(default=None), cursor: int = Query(default=0, ge=0, le=2**63 - 1),
                                 owner: str = Depends(requester)):
        return await collection.personalities(owner, ascended_id, limit, cursor)

    @router.get("/ascendeds/{ascended_id}/presets/{slot}")
    async def get_preset(ascended_id: str, slot: int, owner: str = Depends(requester)):
        return await collection.get_preset(owner, ascended_id, slot)

    @router.put("/ascendeds/{ascended_id}/presets/{slot}")
    async def put_preset(ascended_id: str, slot: int, body: PresetBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await collection.put_preset(owner, key, ascended_id, slot, body.instance_ids)

    @router.post("/encounters", status_code=201)
    async def roll_encounter(owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await encounters.roll(owner, key)

    @router.get("/encounters/{encounter_id}")
    async def get_encounter(encounter_id: str, owner: str = Depends(requester)):
        return await encounters.get(owner, encounter_id)

    @router.post("/encounters/{encounter_id}/decline")
    async def decline_encounter(encounter_id: str, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await encounters.decline(owner, key, encounter_id)

    @router.post("/battles", status_code=201)
    async def start_battle(body: StartBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await coordinator.start(owner, key, encounter_id=body.encounter_id, ascended_id=body.ascended_id,
                                       preset_slot=body.preset_slot, mode=body.mode, emblem_limit=body.emblem_limit)

    @router.get("/battles/{battle_id}")
    async def get_battle(battle_id: str, owner: str = Depends(requester)):
        return await coordinator.view(owner, battle_id)

    @router.post("/battles/{battle_id}/actions")
    async def submit_action(battle_id: str, body: ActionRequest, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await coordinator.submit_action(owner, key, battle_id, round=body.round, revision=body.revision,
                                               action=body.action.model_dump(exclude_none=True))

    @router.post("/battles/{battle_id}/emblem")
    async def answer_emblem(battle_id: str, body: EmblemRequest, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await coordinator.answer_emblem(owner, key, battle_id, round=body.round, revision=body.revision, tier=body.tier)

    @router.post("/battles/{battle_id}/advance")
    async def advance_battle(battle_id: str, body: RoundBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await coordinator.advance(owner, key, battle_id, round=body.round, revision=body.revision)

    @router.post("/battles/{battle_id}/mode")
    async def set_mode(battle_id: str, body: ModeRequest, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await coordinator.set_mode(owner, key, battle_id, round=body.round, revision=body.revision,
                                          mode=body.mode, emblem_limit=body.emblem_limit)

    @router.post("/battles/{battle_id}/forfeit")
    async def forfeit(battle_id: str, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await coordinator.forfeit(owner, key, battle_id)

    @router.get("/shop")
    async def shop_window(owner: str = Depends(requester)):
        return await shop.list_offers(owner)

    @router.post("/shop/purchases", status_code=201)
    async def purchase(body: PurchaseBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        if body.kind == "emblem" and body.tier:
            return await shop.buy_emblems(owner, key, body.tier, body.quantity)
        if body.kind == "copies" and body.rotation is not None and body.slot is not None:
            return await shop.buy_offer(owner, key, body.rotation, body.slot)
        raise HTTPException(400, 'kind must be "emblem" (with tier, quantity) or "copies" (with rotation, slot)')

    @router.post("/ascendeds/{ascended_id}/stars", status_code=201)
    async def add_star(ascended_id: str, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await services.upgrades.add_star(owner, key, ascended_id)

    @router.post("/ascendeds/{ascended_id}/tier", status_code=201)
    async def raise_tier(ascended_id: str, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await services.upgrades.raise_tier(owner, key, ascended_id)

    @router.post("/ascendeds/{ascended_id}/sales", status_code=201)
    async def sell(ascended_id: str, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        return await shop.sell_copy(owner, key, ascended_id)

    return router


def install_error_handlers(app: FastAPI) -> None:
    async def ascended_error(request: Request, error: AscendedError) -> JSONResponse:
        body: dict[str, Any] = {"error": str(error)}
        if isinstance(error, EncounterCooldown):
            body["retry_after"] = error.retry_after
        return JSONResponse(body, status_code=error.status_code)

    async def catalog_error(request: Request, error: CatalogError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=400)

    app.add_exception_handler(AscendedError, ascended_error)
    app.add_exception_handler(CatalogError, catalog_error)


def build_art_router(catalog: Catalog) -> APIRouter:
    """Public: an <img> cannot send the bearer, and the art is not secret. Only catalog ids and the three exact names answer."""
    router = APIRouter()
    headers = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}

    @router.get("/ascended/{ascended_id}/{file}")
    async def sprite(ascended_id: str, file: str):
        path = catalog.sprite_path(ascended_id, file)
        if path is None:
            raise HTTPException(404, "Not Found")
        return FileResponse(path, media_type="image/webp", headers=headers)

    return router


def mount_ascendeds(app: FastAPI, services: AscendedServices) -> None:
    install_error_handlers(app)
    app.include_router(build_router(services))
    app.include_router(build_art_router(services.catalog))
