import pytest

from src.ascension.catalog import CatalogError
from src.ascension.errors import Conflict, InsufficientFunds, InvalidRequest, NothingToSell, SoldOut, WrongPhase
from src.ascension.records import AscendedRecord
from tests.ascension.env import CATALOG, Env, run
from src.ascension.shop_offers import Offer
from tests.ascension.helpers import FixedOffers, battle_record


def make(tmp_path):
    return Env(tmp_path / "s.sqlite3")


async def balance(env, owner="ann"):
    async with env.repo.transaction() as tx:
        return (await tx.get_player(owner)).insignia, await tx.emblem_counts(owner)


def test_emblem_prices_are_a_fifth_of_their_strength(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        bought = await env.shop.buy_emblems("ann", "e1", "rare", 3)
        after = await balance(env)
        await env.close()
        return bought, after

    bought, (insignia, emblems) = run(scenario())
    assert bought["price"] == 120 and insignia == 880 and emblems == {"common": 5, "rare": 3}


def test_forbidden_emblems_are_the_most_expensive(tmp_path):
    prices = {t.id: t.emblem_price for t in CATALOG.tiers}
    assert prices == {"common": 20, "rare": 40, "unique": 80, "royal": 160, "legendary": 320, "forbidden": 640}


def test_not_enough_insignia_changes_nothing(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(insignia=50)
        with pytest.raises(InsufficientFunds):
            await env.shop.buy_emblems("ann", "e1", "rare", 2)
        result = await balance(env)
        await env.close()
        return result

    assert run(scenario()) == (50, {"common": 5})


@pytest.mark.parametrize("quantity", [0, -1, 100, True, "3"])
def test_bad_quantities_are_rejected(tmp_path, quantity):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        with pytest.raises(InvalidRequest):
            await env.shop.buy_emblems("ann", "e1", "common", quantity)
        await env.close()

    run(scenario())


def test_unknown_tier_is_a_catalog_error(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        with pytest.raises(CatalogError):
            await env.shop.buy_emblems("ann", "e1", "gold", 1)
        await env.close()

    run(scenario())








def test_selling_pays_the_value_at_the_current_tier_and_never_changes_it(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 10, 11, 0, tier_id="rare"))
        sale = await env.shop.sell_copy("ann", "s1", "guardian")
        insignia, _ = await balance(env)
        await env.close()
        return sale, insignia

    sale, insignia = run(scenario())
    value = CATALOG.sale_value("guardian", "rare", 11)
    assert sale["value"] == value == insignia and sale["tier_id"] == "rare" and sale["copies"] == 9 and "downgraded" not in sale


def test_selling_never_removes_the_owned_ascended_or_causes_fainting(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        with pytest.raises(NothingToSell):
            await env.shop.sell_copy("ann", "s1", "guardian")  # zero copies
        with pytest.raises(NothingToSell):
            await env.shop.sell_copy("ann", "s2", "sentinel")  # not owned
        await env.give(guardian=AscendedRecord("ann", "guardian", 1, 1, 0))
        await env.shop.sell_copy("ann", "s3", "guardian")
        profile = await env.collection.profile("ann")
        await env.close()
        return profile["ascendeds"][0]

    ascended = run(scenario())
    assert ascended["copies"] == 0 and ascended["fainted"] is False


@pytest.mark.parametrize("ascended_id", [s.id for s in CATALOG.regular_ascendeds()])
@pytest.mark.parametrize("package", ["common", "rare", "unique", "royal", "legendary"])
@pytest.mark.parametrize("tier,level", [("common", 1), ("rare", 7), ("unique", 30), ("royal", 12), ("legendary", 30)])
def test_buying_then_reselling_never_makes_a_profit(ascended_id, package, tier, level):
    owned = AscendedRecord("ann", ascended_id, 3, level, 0, tier_id=tier)
    price, granted = _price(owned, package)
    resale = granted * CATALOG.sale_value(ascended_id, tier, level)
    assert resale < price


def _price(owned, package):
    from src.ascension.shop import ShopService

    return ShopService(None, None, CATALOG, None, None, None).copy_price(owned.ascended_id, owned, package)


def fixed(*offers):
    return lambda tmp: Env(tmp / "s.sqlite3", offers=FixedOffers(*offers))


GUARDIAN_COMMON = Offer(0, "guardian", "common", 2)
SCOUT_RARE = Offer(1, "scout", "rare", 1)


def test_the_window_lists_offers_with_the_servers_price(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON, SCOUT_RARE)(tmp_path)
        await env.start_player()
        window = await env.shop.list_offers("ann")
        await env.close()
        return env, window

    env, window = run(scenario())
    assert window["rotation"] == int(env.clock.now() // 21600.0)
    assert window["seconds_left"] == window["refreshes_at"] - env.clock.now()
    first, second = window["offers"]
    owned = AscendedRecord("ann", "guardian", 0, 1, 0)
    price, granted = _price(owned, "common")
    assert (first["slot"], first["ascended_id"], first["tier_id"]) == (0, "guardian", "common")
    assert (first["price"], first["copies_granted"]) == (price, granted)
    assert first["stock"] == 2 and first["left"] == 2 and second["left"] == 1
    assert "owned_copies" in first


def test_buying_an_offer_grants_copies_and_uses_stock(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON)(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        first = await env.shop.buy_offer("ann", "b1", rotation, 0)
        second = await env.shop.buy_offer("ann", "b2", rotation, 0)
        with pytest.raises(SoldOut):
            await env.shop.buy_offer("ann", "b3", rotation, 0)
        window = await env.shop.list_offers("ann")
        insignia, _ = await balance(env)
        await env.close()
        return first, second, window, insignia

    first, second, window, insignia = run(scenario())
    assert first["kind"] == "copies" and first["left"] == 1 and second["left"] == 0
    assert window["offers"][0]["left"] == 0
    assert insignia == 1000 - first["price"] - second["price"]


def test_buying_a_new_ascended_starts_it_at_level_one(tmp_path):
    async def scenario():
        env = fixed(Offer(0, "sentinel", "common", 1))(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        bought = await env.shop.buy_offer("ann", "c1", rotation, 0)
        profile = await env.collection.profile("ann")
        await env.close()
        return bought, profile

    bought, profile = run(scenario())
    assert bought["price"] == 2 * 1 * 140 and bought["copies_granted"] == 1
    sentinel = next(s for s in profile["ascendeds"] if s["ascended_id"] == "sentinel")
    assert (sentinel["level"], sentinel["copies"], sentinel["tier_id"]) == (1, 0, "common")  # the first copy is the Ascended
    assert profile["insignia"] == 1000 - 280


def test_buying_keeps_an_owned_ascended_level_and_tier_and_prices_at_its_tier(tmp_path):
    async def scenario():
        env = fixed(Offer(0, "guardian", "rare", 1))(tmp_path)
        await env.start_player()
        await env.give(insignia=5000, guardian=AscendedRecord("ann", "guardian", 9, 11, 40, tier_id="rare"))
        rotation = env.offers.rotation_at(env.clock.now())
        bought = await env.shop.buy_offer("ann", "c1", rotation, 0)  # 9 + 2 = 11 spare copies
        profile = await env.collection.profile("ann")
        await env.close()
        return bought, profile

    bought, profile = run(scenario())
    assert bought["copies_granted"] == 2 and "resulting_tier_id" not in bought
    assert bought["price"] == 2 * 2 * CATALOG.sale_value("guardian", "rare", 11)  # 2 x copies x resale at Rare, level 11
    guardian = profile["ascendeds"][0]
    assert (guardian["level"], guardian["xp"], guardian["copies"], guardian["tier_id"]) == (11, 40, 11, "rare")


def test_a_stale_rotation_and_an_unknown_slot_are_refused(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON)(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        with pytest.raises(Conflict, match="refreshed"):
            await env.shop.buy_offer("ann", "b1", rotation - 1, 0)
        with pytest.raises(InvalidRequest):
            await env.shop.buy_offer("ann", "b2", rotation, 9)
        with pytest.raises(InvalidRequest):
            await env.shop.buy_offer("ann", "b3", rotation, True)
        env.clock.advance(21600)
        with pytest.raises(Conflict, match="refreshed"):
            await env.shop.buy_offer("ann", "b4", rotation, 0)
        await env.close()

    run(scenario())


def test_a_new_rotation_restores_stock_and_drops_old_counts(tmp_path):
    async def scenario():
        env = fixed(Offer(0, "guardian", "common", 1))(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        first_rotation = env.offers.rotation_at(env.clock.now())
        await env.shop.buy_offer("ann", "b1", first_rotation, 0)
        env.clock.advance(21600)
        second_rotation = env.offers.rotation_at(env.clock.now())
        again = await env.shop.buy_offer("ann", "b2", second_rotation, 0)
        async with env.repo.transaction() as tx:
            old = await tx.shop_bought("ann", first_rotation)
        await env.close()
        return again, old

    again, old = run(scenario())
    assert again["left"] == 0 and old == {}


def test_a_fighting_ascended_cannot_be_bought_or_sold_but_others_can(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON, SCOUT_RARE)(tmp_path)
        await env.start_player()
        await env.give(insignia=5000, guardian=AscendedRecord("ann", "guardian", 3, 1, 0))
        async with env.repo.transaction() as tx:
            await tx.add_battle(battle_record())  # its fighter is the guardian Ascended by default
        rotation = env.offers.rotation_at(env.clock.now())
        with pytest.raises(WrongPhase):
            await env.shop.buy_offer("ann", "b1", rotation, 0)
        with pytest.raises(WrongPhase):
            await env.shop.sell_copy("ann", "s1", "guardian")
        await env.shop.buy_offer("ann", "b2", rotation, 1)
        await env.shop.buy_emblems("ann", "e1", "common", 1)
        await env.close()

    run(scenario())


def test_a_retried_offer_purchase_is_charged_once(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON)(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        first = await env.shop.buy_offer("ann", "same", rotation, 0)
        second = await env.shop.buy_offer("ann", "same", rotation, 0)
        insignia, _ = await balance(env)
        await env.close()
        return first, second, insignia

    first, second, insignia = run(scenario())
    assert first == second and insignia == 1000 - first["price"]


def test_a_retried_emblem_purchase_is_charged_once(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        first = await env.shop.buy_emblems("ann", "same", "common", 2)
        second = await env.shop.buy_emblems("ann", "same", "common", 2)
        result = await balance(env)
        await env.close()
        return first, second, result

    first, second, (insignia, emblems) = run(scenario())
    assert first == second and insignia == 960 and emblems == {"common": 7}


def test_not_enough_insignia_keeps_the_stock(tmp_path):
    async def scenario():
        env = fixed(SCOUT_RARE)(tmp_path)
        await env.start_player()
        rotation = env.offers.rotation_at(env.clock.now())
        with pytest.raises(InsufficientFunds):
            await env.shop.buy_offer("ann", "b1", rotation, 1)
        window = await env.shop.list_offers("ann")
        await env.close()
        return window

    assert run(scenario())["offers"][0]["left"] == 1
