import dataclasses
import uuid

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.laya_client import LayaClient
from src.ascension.api import mount_ascendeds
from src.ascension.composition import build_ascended_services
from src.ascension.runtime import SeededRandom
from tests.conftest import signed_in
from tests.fake_laya import FakeEngine
from tests.ascension.helpers import FixedClock

TOKEN = "t0ken"
def headers(client, owner="ann", key=True):
    result = signed_in(client.app, owner) if owner else {}
    if key is True:
        result["Idempotency-Key"] = f"k{uuid.uuid4().hex}"
    elif key:
        result["Idempotency-Key"] = key
    return result


@pytest.fixture
def clock():
    return FixedClock()


@pytest.fixture
def client(config, tmp_path, clock):
    config = dataclasses.replace(config, database_path=tmp_path / "api.sqlite3")
    app = create_app()
    services = build_ascended_services(config, LayaClient(FakeEngine(fail=True)), clock=clock, rng=SeededRandom(5))
    mount_ascendeds(app, services)
    with TestClient(app) as test_client:
        yield test_client


def start_profile(client, owner="ann", starter="guardian"):
    response = client.post("/ascension/profile", json={"starter_ascended_id": starter}, headers=headers(client, owner))
    assert response.status_code == 201, response.text
    return response.json()


# -- access --------------------------------------------------------------------------

def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("h", [{}, {"X-Requester-Username": "ann"}, {"X-Internal-Token": "wrong", "X-Requester-Username": "ann"}])
def test_bearer_auth_is_required(client, h):
    assert client.get("/ascension/profile", headers=h).status_code == 401


def test_a_bearer_session_is_required(client):
    response = client.get("/ascension/profile", headers=headers(client, owner=None))
    assert response.status_code == 401 and response.json()["error"] == "Not signed in"


def test_mutations_need_an_idempotency_key(client):
    response = client.post("/ascension/profile", json={"starter_ascended_id": "guardian"}, headers=headers(client, key=False))
    assert response.status_code == 400 and "Idempotency-Key" in response.json()["error"]


def test_the_catalog_is_readable_and_complete(client):
    data = client.get("/ascension/catalog", headers=headers(client, owner="anyone")).json()
    assert len(data["ascendeds"]) == 8 and [t["id"] for t in data["tiers"]][-1] == "forbidden"
    assert {s["id"] for s in data["ascendeds"] if s["starter"]} == {"guardian", "striker", "scout"}
    assert len(data["personalities"]) == 22
    assert all("enchant" in s["ascension_types"] for s in data["ascendeds"])
    assert next(s for s in data["ascendeds"] if s["id"] == "twoychi")["ascension_types"] == ["enchant", "divine"]


def test_catalog_explains_conditional_personalities(client):
    data = client.get("/ascension/catalog", headers=headers(client)).json()
    reckless = next(p for p in data["personalities"] if p["id"] == "RECKLESS")
    assert reckless["rules"] == [{"when": {"own_hp_under": 0.5}, "multiply": {"ATTACK": 1.6, "DEFENSE": 0.7, "FEAR": 0.5}}]
    assert data["personality_off_mood_factor"] == 0.5


# -- profile, personalities, presets -------------------------------------------------

def test_profile_creation_is_once_and_idempotent(client):
    first = client.post("/ascension/profile", json={"starter_ascended_id": "scout"}, headers=headers(client, key="same"))
    again = client.post("/ascension/profile", json={"starter_ascended_id": "scout"}, headers=headers(client, key="same"))
    other = client.post("/ascension/profile", json={"starter_ascended_id": "scout"}, headers=headers(client, ))
    clash = client.post("/ascension/profile", json={"starter_ascended_id": "striker"}, headers=headers(client, key="same"))
    assert first.status_code == again.status_code == 201 and first.json() == again.json()
    assert other.status_code == 409 and clash.status_code == 409
    profile = client.get("/ascension/profile", headers=headers(client, )).json()
    assert profile["emblems"] == {"common": 5} and profile["insignia"] == 0 and profile["ascendeds"][0]["ascended_id"] == "scout"
    assert profile["ascendeds"][0]["ascension_types"] == ["enchant"]


def test_a_bad_starter_and_unknown_fields_are_400(client):
    assert client.post("/ascension/profile", json={"starter_ascended_id": "forbidden"}, headers=headers(client, )).status_code == 400
    assert client.post("/ascension/profile", json={"starter_ascended_id": "guardian", "insignia": 9999}, headers=headers(client, )).status_code == 400
    assert client.post("/ascension/profile", json={}, headers=headers(client, )).status_code == 400


def test_profiles_are_private_to_their_owner(client):
    start_profile(client, "ann")
    assert client.get("/ascension/profile", headers=headers(client, "bob")).status_code == 404
    assert client.get("/ascension/ascendeds/guardian/personalities", headers=headers(client, "bob")).status_code == 404


def test_personalities_and_presets_over_http(client):
    start_profile(client)
    pool = client.get("/ascension/ascendeds/guardian/personalities", headers=headers(client, )).json()
    ids = [p["id"] for p in pool["items"]]
    assert len(ids) == 1 and pool["next_cursor"] is None
    put = client.put("/ascension/ascendeds/guardian/presets/2", json={"instance_ids": ids}, headers=headers(client, ))
    assert put.status_code == 200 and client.get("/ascension/ascendeds/guardian/presets/2", headers=headers(client, )).json()["instance_ids"] == ids
    assert client.put("/ascension/ascendeds/guardian/presets/2", json={"instance_ids": ["nope"]}, headers=headers(client, )).status_code == 400
    assert client.put("/ascension/ascendeds/guardian/presets/9", json={"instance_ids": []}, headers=headers(client, )).status_code == 400
    assert client.get("/ascension/ascendeds/guardian/personalities?limit=500", headers=headers(client, )).status_code == 400


# -- encounters ----------------------------------------------------------------------

def test_encounter_rolls_respect_the_cooldown(client, clock):
    start_profile(client)
    first = client.post("/ascension/encounters", headers=headers(client, ))
    early = client.post("/ascension/encounters", headers=headers(client, ))
    assert first.status_code == 201 and "personalities" not in first.text
    assert early.status_code == 409 and early.json()["retry_after"] == pytest.approx(30)
    clock.advance(31)
    assert client.post("/ascension/encounters", headers=headers(client, )).status_code == 201


def test_decline_over_http(client):
    start_profile(client)
    encounter = client.post("/ascension/encounters", headers=headers(client, )).json()
    assert client.post(f"/ascension/encounters/{encounter['id']}/decline", headers=headers(client, )).json()["status"] == "declined"
    assert client.get(f"/ascension/encounters/{encounter['id']}", headers=headers(client, "bob")).status_code == 404


# -- battles -------------------------------------------------------------------------

def open_battle(client, mode="manual", **extra):
    start_profile(client)
    encounter = client.post("/ascension/encounters", headers=headers(client, )).json()
    body = {"encounter_id": encounter["id"], "ascended_id": "guardian", "preset_slot": 1, "mode": mode, **extra}
    response = client.post("/ascension/battles", json=body, headers=headers(client, ))
    assert response.status_code == 201, response.text
    return response.json()


def test_a_battle_can_be_started_played_and_forfeited(client):
    view = open_battle(client)
    assert view["phase"] == "choosing" and any(a["kind"] == "attack" for a in view["actions"])
    action = {"round": view["round"], "revision": view["revision"], "action": {"kind": "attack"}}
    after = client.post(f"/ascension/battles/{view['id']}/actions", json=action, headers=headers(client, ))
    assert after.status_code == 200 and after.json()["revision"] == 2 and len(after.json()["history"]) == 1
    if after.json()["status"] == "active":
        done = client.post(f"/ascension/battles/{view['id']}/forfeit", headers=headers(client, )).json()
        assert done["status"] == "terminal" and done["result"]["kind"] == "forfeited"
        assert client.post(f"/ascension/battles/{view['id']}/forfeit", headers=headers(client, )).status_code == 409


def test_a_stale_action_is_a_409_and_a_retry_is_not_repeated(client):
    view = open_battle(client)
    body = {"round": 1, "revision": 1, "action": {"kind": "attack"}}
    first = client.post(f"/ascension/battles/{view['id']}/actions", json=body, headers=headers(client, key="once"))
    retry = client.post(f"/ascension/battles/{view['id']}/actions", json=body, headers=headers(client, key="once"))
    stale = client.post(f"/ascension/battles/{view['id']}/actions", json=body, headers=headers(client, ))
    assert first.status_code == retry.status_code == 200 and first.json() == retry.json()
    assert stale.status_code == 409


def test_clients_cannot_send_rewards_or_chances(client):
    view = open_battle(client)
    cheat = {"round": 1, "revision": 1, "action": {"kind": "attack", "damage": 9999}}
    assert client.post(f"/ascension/battles/{view['id']}/actions", json=cheat, headers=headers(client, )).status_code == 400
    cheat = {"round": 1, "revision": 1, "action": {"kind": "attack"}, "xp": 5000}
    assert client.post(f"/ascension/battles/{view['id']}/actions", json=cheat, headers=headers(client, )).status_code == 400


def test_illegal_actions_and_wrong_modes(client):
    view = open_battle(client)
    nope = {"round": 1, "revision": 1, "action": {"kind": "ability", "ability_id": "unknown"}}
    assert client.post(f"/ascension/battles/{view['id']}/actions", json=nope, headers=headers(client, )).status_code == 400
    advance = client.post(f"/ascension/battles/{view['id']}/advance", json={"round": 1, "revision": 1}, headers=headers(client, ))
    assert advance.status_code == 409  # manual battles wait for the player


def test_autonomous_advance_and_mode_switch(client):
    view = open_battle(client, mode="autonomous", emblem_limit="common")
    played = client.post(f"/ascension/battles/{view['id']}/advance", json={"round": 1, "revision": 1}, headers=headers(client, ))
    assert played.status_code == 200
    data = played.json()
    if data["phase"] == "awaiting_emblem":  # the Ascended chose CATCH: the player has five seconds to pick an EMBLEM
        assert data["history"] == [] and data["prompt"]["seconds_left"] == 5.0
        body = {"round": data["round"], "revision": data["revision"], "mode": "manual"}
        assert client.post(f"/ascension/battles/{view['id']}/mode", json=body, headers=headers(client, )).status_code == 409
        return
    assert len(data["history"]) == 1
    if data["status"] == "active":
        body = {"round": data["round"], "revision": data["revision"], "mode": "manual"}
        assert client.post(f"/ascension/battles/{view['id']}/mode", json=body, headers=headers(client, )).json()["mode"] == "manual"


def test_battles_are_private_to_their_owner(client):
    view = open_battle(client)
    start_profile(client, "bob")
    assert client.get(f"/ascension/battles/{view['id']}", headers=headers(client, "bob")).status_code == 404
    assert client.post(f"/ascension/battles/{view['id']}/forfeit", headers=headers(client, "bob")).status_code == 404
    assert client.get("/ascension/battles/missing", headers=headers(client, )).status_code == 404


def test_a_second_battle_is_refused_while_one_is_active(client):
    open_battle(client)
    assert client.post("/ascension/encounters", headers=headers(client, )).status_code == 409


# -- shop ----------------------------------------------------------------------------

def test_shop_over_http(client):
    start_profile(client)
    poor = client.post("/ascension/shop/purchases", json={"kind": "emblem", "tier": "rare", "quantity": 1}, headers=headers(client, ))
    assert poor.status_code == 409
    assert client.post("/ascension/shop/purchases", json={"kind": "copies", "ascended_id": "sentinel", "tier": "common"}, headers=headers(client, )).status_code == 400
    assert client.post("/ascension/shop/purchases", json={"kind": "copies"}, headers=headers(client, )).status_code == 400
    assert client.post("/ascension/shop/purchases", json={"kind": "stock", "tier": "rare"}, headers=headers(client, )).status_code == 400
    assert client.post("/ascension/shop/purchases", json={"kind": "emblem", "tier": "gold", "quantity": 1}, headers=headers(client, )).status_code == 400
    assert client.post("/ascension/ascendeds/guardian/sales", headers=headers(client, )).status_code == 409  # nothing to sell
    assert client.post("/ascension/ascendeds/dragon/sales", headers=headers(client, )).status_code == 400


def test_the_shop_lists_offers_and_refuses_a_player_without_insignia(client):
    start_profile(client)
    shop = client.get("/ascension/shop", headers=headers(client, key=False))
    assert shop.status_code == 200, shop.text
    body = shop.json()
    assert len(body["offers"]) == 5 and body["seconds_left"] > 0
    offer = body["offers"][0]
    poor = client.post("/ascension/shop/purchases", json={"kind": "copies", "rotation": body["rotation"], "slot": offer["slot"]}, headers=headers(client))
    assert poor.status_code == 409  # a new player has no Insignia


def test_a_stale_rotation_and_a_missing_slot_are_refused_over_http(client):
    start_profile(client)
    body = client.get("/ascension/shop", headers=headers(client, key=False)).json()
    stale = client.post("/ascension/shop/purchases", json={"kind": "copies", "rotation": body["rotation"] - 1, "slot": 0}, headers=headers(client))
    assert stale.status_code == 409 and "refreshed" in stale.json()["error"]
    missing = client.post("/ascension/shop/purchases", json={"kind": "copies", "rotation": body["rotation"], "slot": 99}, headers=headers(client))
    assert missing.status_code == 400


def test_the_shop_needs_a_profile(client):
    assert client.get("/ascension/shop", headers=headers(client, "newbie", key=False)).status_code == 404


def test_the_catalog_lists_each_ascended_s_sprites(client):
    data = client.get("/ascension/catalog", headers=headers(client, key=False)).json()
    by_id = {s["id"]: s for s in data["ascendeds"]}
    assert by_id["guardian"]["art"] == {
        "main_card": "/ascended/guardian/sprite_main_card.webp",
        "preview_card": "/ascended/guardian/sprite_preview_card.webp",
        "battle": "/ascended/guardian/sprite_battle.webp",
        "focus": 21, "focus_preview": 50, "animation": None,
    }
    assert by_id["bruiser"]["art"]["main_card"] is None and by_id["bruiser"]["art"]["battle"] is None


def test_an_ascended_with_a_sheet_lists_its_animation(client):
    data = client.get("/ascension/catalog", headers=headers(client, key=False)).json()
    animation = {s["id"]: s for s in data["ascendeds"]}["twoychi"]["art"]["animation"]
    assert animation["url"] == "/ascended/twoychi/spreadsheet_animation.webp"
    assert (animation["columns"], animation["rows"]) == (4, 6)
    assert animation["states"]["attack"] == {"row": 1, "frames": 4, "frame_ms": 100, "loop": False}
    sheet = client.get(animation["url"])
    assert sheet.status_code == 200 and sheet.headers["content-type"] == "image/webp"


def test_sprites_are_public_and_never_stale(client):
    response = client.get("/ascended/guardian/sprite_battle.webp")
    assert response.status_code == 200 and response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "no-cache" and response.headers["etag"]
    assert response.content[:4] == b"RIFF"


@pytest.mark.parametrize("path", [
    "/ascended/nobody/sprite_battle.webp", "/ascended/bruiser/sprite_battle.webp", "/ascended/guardian/catalog.json",
    "/ascended/guardian/sprite_battle.png", "/ascended/guardian/%2e%2e/guardian/sprite_battle.webp",
    "/ascended/%2e%2e/configs/ascension_catalog.json", "/ascended/guardian/..%5ccatalog.json", "/ascended/guardian",
])
def test_any_other_sprite_request_is_a_404_not_a_page(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")


# -- stars and tiers -----------------------------------------------------------------

def test_the_catalog_publishes_the_star_ladder_and_each_start_tier(client):
    data = client.get("/ascension/catalog", headers=headers(client, owner="anyone")).json()
    assert [(t["id"], t["stars_to_advance"], t["essence_cost"]) for t in data["tiers"]] == [
        ("common", 1, 1), ("rare", 2, 2), ("unique", 3, 3), ("royal", 5, 4), ("legendary", None, 5), ("forbidden", None, 10)]
    assert all("copy_threshold" not in t for t in data["tiers"])
    assert {s["id"]: s["start_tier"] for s in data["ascendeds"]}["forbidden"] == "forbidden"


def test_stars_and_tier_over_http(client):
    start_profile(client)
    profile = client.get("/ascension/profile", headers=headers(client, key=False)).json()
    owned = profile["ascendeds"][0]
    assert profile["essences"] == {} and (owned["tier_id"], owned["stars"], owned["stars_needed"]) == ("common", 0, 1)
    assert owned["can_star_up"] is False and owned["can_tier_up"] is False
    assert client.post(f"/ascension/ascendeds/{owned['ascended_id']}/stars", headers=headers(client)).status_code == 409  # no copy or essence
    assert client.post(f"/ascension/ascendeds/{owned['ascended_id']}/tier", headers=headers(client)).status_code == 409  # no stars
    assert client.post("/ascension/ascendeds/sentinel/stars", headers=headers(client)).status_code == 404  # not owned
    assert client.post("/ascension/ascendeds/dragon/tier", headers=headers(client)).status_code == 404


# -- ability trees -------------------------------------------------------------------

def test_the_catalog_lists_every_tree(client):
    data = client.get("/ascension/catalog", headers=headers(client, owner="anyone")).json()
    guardian = next(s for s in data["ascendeds"] if s["id"] == "guardian")
    ids = {n["id"] for n in guardian["tree"]}
    assert {"guardian_bulwark", "guardian_passive"} <= ids
    assert all({"id", "kind", "x", "y", "requires", "unlock_level", "cost", "root"} <= set(n) for n in guardian["tree"])


@pytest.fixture
def tree_client(config, tmp_path, clock):
    from src.ascension.catalog import Catalog
    from tests.ascension.env import load_raw
    from tests.ascension.test_trees import TREE

    raw = load_raw()
    next(s for s in raw["ascendeds"] if s["id"] == "guardian")["tree"] = TREE
    config = dataclasses.replace(config, database_path=tmp_path / "tree_api.sqlite3")
    app = create_app()
    services = build_ascended_services(config, LayaClient(FakeEngine(fail=True)), catalog=Catalog(raw),
                                      clock=clock, rng=SeededRandom(5))
    mount_ascendeds(app, services)
    with TestClient(app) as test_client:
        yield test_client


def test_trees_and_loadouts_over_http(tree_client):
    client = tree_client
    start_profile(client)
    h = lambda: headers(client)  # noqa: E731
    tree = client.get("/ascension/ascendeds/guardian/tree", headers=headers(client, key=False)).json()
    assert tree["loadout"]["a1"] == "guardian_bulwark" and tree["loadout"]["p1"] == "guardian_passive"
    assert all(n["state"] in ("learned", "learnable", "locked") for n in tree["nodes"])
    assert client.get("/ascension/ascendeds/sentinel/tree", headers=headers(client, key=False)).status_code == 404
    assert client.post("/ascension/ascendeds/guardian/tree/nope/learn", headers=h()).status_code == 400
    assert client.post("/ascension/ascendeds/guardian/tree/guardian_bulwark/learn", headers=h()).status_code == 409  # a root
    locked = next(n["id"] for n in tree["nodes"] if n["state"] == "locked")
    assert client.post(f"/ascension/ascendeds/guardian/tree/{locked}/learn", headers=h()).status_code == 409
    saved = client.put("/ascension/ascendeds/guardian/loadout", json={"abilities": ["guardian_heavy_blow", "guardian_bulwark"], "passive": None}, headers=h())
    assert saved.status_code == 200 and saved.json()["abilities"] == ["guardian_heavy_blow", "guardian_bulwark"]
    again = client.get("/ascension/ascendeds/guardian/tree", headers=headers(client, key=False)).json()
    assert again["loadout"] == {"a1": "guardian_heavy_blow", "a2": "guardian_bulwark", "a3": None, "p1": None}
    assert client.put("/ascension/ascendeds/guardian/loadout", json={"abilities": []}, headers=h()).status_code == 400
    assert client.put("/ascension/ascendeds/guardian/loadout", json={"abilities": ["x"], "extra": 1}, headers=h()).status_code == 400
