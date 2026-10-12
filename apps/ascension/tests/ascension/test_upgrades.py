import pytest

from src.ascension.errors import InsufficientCopies, InsufficientEssence, InvalidRequest, NotFound, UpgradeNotReady
from src.ascension.records import AscendedRecord
from tests.ascension.env import Env, run


def make(tmp_path):
    return Env(tmp_path / "u.sqlite3")


async def state(env, ascended_id="guardian"):
    async with env.repo.transaction() as tx:
        return await tx.get_ascended("ann", ascended_id), await tx.essence_counts("ann")


def test_a_star_costs_one_spare_copy_and_the_tiers_essence(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 2, 3, 40, tier_id="rare"))
        await env.give_essence("rare", 5)
        result = await env.upgrades.add_star("ann", "k1", "guardian")
        saved = await state(env)
        await env.close()
        return result, saved

    result, (ascended, essences) = run(scenario())
    assert (ascended.stars, ascended.copies, ascended.tier_id, ascended.level, ascended.xp) == (1, 1, "rare", 3, 40)
    assert essences == {"rare": 3}  # Rare costs 2 essence a star
    assert result["stars"] == 1 and result["stars_needed"] == 2 and result["essence_spent"] == 2 and result["can_tier_up"] is False


def test_a_star_needs_a_copy_and_enough_essence_and_changes_nothing_when_refused(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 0, 1, 0))
        await env.give_essence("common", 5)
        with pytest.raises(InsufficientCopies):
            await env.upgrades.add_star("ann", "k1", "guardian")
        await env.give(guardian=AscendedRecord("ann", "guardian", 1, 1, 0))
        await env.give_essence("common", -5)
        with pytest.raises(InsufficientEssence):
            await env.upgrades.add_star("ann", "k2", "guardian")
        saved = await state(env)
        await env.close()
        return saved

    ascended, essences = run(scenario())
    assert (ascended.copies, ascended.stars) == (1, 0) and essences == {}


def test_stars_stop_at_the_tiers_limit_and_the_tier_then_rises(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 5, 1, 0))  # Common: 1 star, 1 essence each
        await env.give_essence("common", 5)
        with pytest.raises(UpgradeNotReady):
            await env.upgrades.raise_tier("ann", "k0", "guardian")
        star = await env.upgrades.add_star("ann", "k1", "guardian")
        with pytest.raises(UpgradeNotReady, match="stars are full"):
            await env.upgrades.add_star("ann", "k2", "guardian")
        raised = await env.upgrades.raise_tier("ann", "k3", "guardian")
        saved = await state(env)
        await env.close()
        return star, raised, saved

    star, raised, (ascended, essences) = run(scenario())
    assert star["can_tier_up"] is True
    assert (raised["from_tier_id"], raised["tier_id"], raised["stars"]) == ("common", "rare", 0)
    assert (ascended.tier_id, ascended.stars, ascended.copies) == ("rare", 0, 4) and essences == {"common": 4}


def test_the_top_of_the_ladder_takes_no_stars_and_cannot_rise(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 5, 1, 0, tier_id="legendary"),
                       cindrax=AscendedRecord("ann", "cindrax", 5, 1, 0))
        await env.give_essence("legendary", 9)
        await env.give_essence("cindrax", 99)
        for ascended_id in ("guardian", "cindrax"):
            with pytest.raises(UpgradeNotReady):
                await env.upgrades.add_star("ann", f"s-{ascended_id}", ascended_id)
            with pytest.raises(InvalidRequest):
                await env.upgrades.raise_tier("ann", f"t-{ascended_id}", ascended_id)
        await env.close()

    run(scenario())


def test_you_cannot_upgrade_an_ascended_you_do_not_own(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        for call in (env.upgrades.add_star, env.upgrades.raise_tier):
            with pytest.raises(NotFound):
                await call("ann", f"k-{call.__name__}", "sentinel")
            with pytest.raises(NotFound):
                await call("ann", f"x-{call.__name__}", "nobody")
        await env.close()

    run(scenario())


def test_repeating_a_star_request_with_the_same_key_spends_once(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 3, 1, 0))
        await env.give_essence("common", 3)
        first = await env.upgrades.add_star("ann", "same", "guardian")
        again = await env.upgrades.add_star("ann", "same", "guardian")
        saved = await state(env)
        await env.close()
        return first, again, saved

    first, again, (ascended, essences) = run(scenario())
    assert first == again and (ascended.stars, ascended.copies) == (1, 2) and essences == {"common": 2}


def test_the_profile_shows_stars_costs_and_what_can_be_done(tmp_path):
    async def scenario():
        env = make(tmp_path)
        await env.start_player()
        await env.give(guardian=AscendedRecord("ann", "guardian", 1, 1, 0, tier_id="rare", stars=1))
        await env.give_essence("rare", 2)
        before = await env.collection.profile("ann")
        await env.upgrades.add_star("ann", "k1", "guardian")
        after = await env.collection.profile("ann")
        await env.close()
        return before, after

    before, after = run(scenario())
    one = before["ascendeds"][0]
    assert before["essences"] == {"rare": 2}
    assert (one["tier_id"], one["stars"], one["stars_needed"], one["star_essence_cost"], one["next_tier_id"]) == ("rare", 1, 2, 2, "unique")
    assert one["can_star_up"] is True and one["can_tier_up"] is False
    two = after["ascendeds"][0]
    assert after["essences"] == {} and two["stars"] == 2 and two["can_star_up"] is False and two["can_tier_up"] is True
