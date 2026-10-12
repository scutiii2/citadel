import pytest
from src.ascension.catalog import Catalog, CatalogError
from src.ascension.errors import InvalidRequest, NotFound, BattleInProgress
from src.ascension.records import AscendedRecord
from tests.ascension.env import Env, run, load_raw
from tests.ascension.helpers import battle_record


@pytest.mark.parametrize(
    "field,value", [("squad_size", 0), ("bench_xp_pool_factor", 1), ("bench_xp_pool_factor", -0.1)]
)
def test_invalid_squad_economy(field, value):
    raw = load_raw()
    raw["economy"][field] = value
    with pytest.raises(CatalogError):
        Catalog(raw)


def test_starter_profile_and_squad_replacement(tmp_path):
    async def work():
        env = Env(tmp_path / "db")
        try:
            profile = await env.start_player()
            assert profile["squad"] == ["guardian"]
            assert profile["squad_size"] == 5
            assert profile["ascendeds"][0]["in_squad"]
            from src.ascension.squad import SquadService

            service = SquadService(env.repo, env.writer, env.catalog)
            await env.give(scout=AscendedRecord("ann", "scout", 0, 1, 0))
            key = env.key()
            result = await service.put("ann", key, ["scout", "guardian"])
            assert result == {"ascended_ids": ["scout", "guardian"], "size": 5}
            await service.put("ann", env.key(), ["guardian"])
            assert await service.put("ann", key, ["scout", "guardian"]) == result
            assert (await service.get("ann"))["ascended_ids"] == ["guardian"]
        finally:
            await env.close()

    run(work())


@pytest.mark.parametrize(
    "ids,error",
    [
        ([], InvalidRequest),
        (["guardian"] * 6, InvalidRequest),
        (["guardian", "guardian"], InvalidRequest),
        (["scout"], NotFound),
        (["missing"], NotFound),
        ([1], InvalidRequest),
        ("guardian", InvalidRequest),
    ],
)
def test_squad_invalid_requests(tmp_path, ids, error):
    async def work():
        env = Env(tmp_path / "db")
        try:
            await env.start_player()
            from src.ascension.squad import SquadService

            service = SquadService(env.repo, env.writer, env.catalog)
            with pytest.raises(error):
                await service.put("ann", env.key(), ids)
        finally:
            await env.close()

    run(work())


def test_squad_locked_during_battle_and_auto_equip(tmp_path):
    async def work():
        env = Env(tmp_path / "db")
        try:
            await env.start_player()
            from src.ascension.squad import SquadService

            service = SquadService(env.repo, env.writer, env.catalog)
            async with env.repo.transaction() as tx:
                await SquadService.auto_equip(tx, "ann", "guardian", 2)
                await SquadService.auto_equip(tx, "ann", "scout", 2)
                await SquadService.auto_equip(tx, "ann", "striker", 2)
                assert await tx.get_squad("ann") == ("guardian", "scout")
                await tx.add_battle(battle_record())
            with pytest.raises(BattleInProgress):
                await service.put("ann", env.key(), ["guardian"])
            async with env.repo.transaction() as tx:
                await tx.delete_player_data("ann")
                assert await tx.get_squad("ann") == ()
        finally:
            await env.close()

    run(work())


@pytest.mark.parametrize("xp,count,expected", [(201, 4, 25), (25, 4, 3), (1, 1, 0), (20, 0, 0)])
def test_share_rounding(xp, count, expected):
    from tests.ascension.test_progression import progression

    assert progression.squad_share(xp, count) == expected


@pytest.mark.parametrize("terminal", ["won", "captured", "knocked_out", "forfeited"])
def test_only_existing_squad_members_share_xp(tmp_path, terminal):
    from tests.ascension.test_progression import build_battle
    from tests.ascension.helpers import ScriptedRandom

    async def work():
        env = Env(tmp_path / "db")
        try:
            await env.start_player()
            bench = ["scout", "striker", "channeler", "cindrax"]
            async with env.repo.transaction() as tx:
                for a in [*bench, "twoychi"]:
                    await tx.put_ascended(AscendedRecord("ann", a, 0, 1, 0, faint_until=env.clock.now() + 100))
                await tx.set_squad("ann", ["guardian", *bench])
                result = await env.progression.apply_terminal(tx, build_battle(), terminal, ScriptedRandom(0))
                assert (await tx.get_ascended("ann", "twoychi")).xp == 0
                if terminal in ("won", "captured"):
                    assert result["xp"] == 200
                    assert len(result["squad_xp"]) == 4
                    assert all(row["xp"] == 25 for row in result["squad_xp"])
                    for a in bench:
                        assert (await tx.get_ascended("ann", a)).xp == 25
                else:
                    for a in bench:
                        assert (await tx.get_ascended("ann", a)).xp == 0
        finally:
            await env.close()

    run(work())


@pytest.mark.parametrize("version", [2, 3, 4, 5])
def test_migration_backfills_squad_in_level_order(tmp_path, version):
    import sqlite3
    from src.ascension.repository import BASE_SCHEMA, SHOP_SCHEMA, STAR_MIGRATION, TREE_SCHEMA, SqliteAscendedRepository

    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        schema = (
            BASE_SCHEMA
            + (SHOP_SCHEMA if version >= 3 else "")
            + (STAR_MIGRATION if version >= 4 else "")
            + (TREE_SCHEMA if version >= 5 else "")
        )
        conn.executescript(schema)
        conn.execute(f"PRAGMA user_version = {version}")
        for a, level in [("guardian", 1), ("striker", 8), ("scout", 8)]:
            conn.execute("INSERT INTO ascendeds (owner,ascended_id,copies,level,xp) VALUES ('ann',?,0,?,0)", (a, level))
        conn.execute("INSERT INTO ascendeds (owner,ascended_id,copies,level,xp) VALUES ('bob','guardian',0,1,0)")

    async def work():
        repo = SqliteAscendedRepository(db, squad_size=2)
        try:
            async with repo.transaction() as tx:
                assert await tx.get_squad("ann") == ("scout", "striker")
                assert await tx.get_squad("bob") == ("guardian",)
                assert await tx.get_loadout("ann", "guardian") == {}
        finally:
            await repo.close()

    run(work())
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6


def test_non_squad_fighter_cannot_start(tmp_path):
    from tests.ascension.test_coordinator import encounter

    async def work():
        env = Env(tmp_path / "db")
        try:
            await env.start_player()
            await env.give(scout=AscendedRecord("ann", "scout", 0, 1, 0))
            eid = await encounter(env)
            coord = env.coordinator()
            with pytest.raises(InvalidRequest, match="not in your squad"):
                await coord.start(
                    "ann",
                    env.key(),
                    encounter_id=eid,
                    ascended_id="scout",
                    preset_slot=None,
                    mode="manual",
                    emblem_limit=None,
                )
            async with env.repo.transaction() as tx:
                await tx.set_squad("ann", ["scout"])
            result = await coord.start(
                "ann",
                env.key(),
                encounter_id=eid,
                ascended_id="scout",
                preset_slot=None,
                mode="manual",
                emblem_limit=None,
            )
            assert result["player"]["ascended_id"] == "scout"
        finally:
            await env.close()

    run(work())


@pytest.mark.parametrize("source", ["capture", "shop"])
@pytest.mark.parametrize("full", [False, True])
def test_new_ownership_auto_equips_only_with_room(tmp_path, source, full):
    from tests.ascension.test_progression import build_battle
    from tests.ascension.helpers import ScriptedRandom, FixedOffers
    from src.ascension.shop_offers import Offer

    async def work():
        env = Env(tmp_path / "db", offers=FixedOffers(Offer(1, "sentinel", "unique", 2)))
        try:
            await env.start_player()
            if full:
                async with env.repo.transaction() as tx:
                    ids = ["guardian", "scout", "striker", "channeler", "cindrax"]
                    for a in ids[1:]:
                        await tx.put_ascended(AscendedRecord("ann", a, 0, 1, 0))
                    await tx.set_squad("ann", ids)
            if source == "capture":
                async with env.repo.transaction() as tx:
                    await env.progression.apply_terminal(
                        tx, build_battle(wild_ascended="sentinel"), "captured", ScriptedRandom(0)
                    )
            else:
                await env.give(insignia=100000)
                await env.shop.buy_offer("ann", env.key(), env.offers.rotation_at(env.clock.now()), 1)
            async with env.repo.transaction() as tx:
                assert await tx.get_ascended("ann", "sentinel") is not None
                squad = await tx.get_squad("ann")
                assert ("sentinel" in squad) is (not full)
                assert len(squad) == (5 if full else 2)
        finally:
            await env.close()

    run(work())


def test_no_bench_and_capped_bench_result(tmp_path):
    from tests.ascension.test_progression import build_battle
    from tests.ascension.helpers import ScriptedRandom

    async def work():
        env = Env(tmp_path / "db")
        try:
            await env.start_player()
            async with env.repo.transaction() as tx:
                result = await env.progression.apply_terminal(tx, build_battle(), "won", ScriptedRandom())
                assert result["squad_xp"] == []
                await tx.put_ascended(AscendedRecord("ann", "scout", 0, 30, 0))
                await tx.set_squad("ann", ["guardian", "scout", "missing"])
                result = await env.progression.apply_terminal(tx, build_battle(), "won", ScriptedRandom())
                assert result["squad_xp"] == [
                    {
                        "ascended_id": "scout",
                        "name": env.catalog.ascended("scout").name,
                        "xp": 50,
                        "level_before": 30,
                        "level_after": 30,
                    }
                ]
                assert (await tx.get_ascended("ann", "scout")).xp == 0
        finally:
            await env.close()

    run(work())


def test_shop_cannot_auto_equip_during_active_battle(tmp_path):
    from tests.ascension.helpers import FixedOffers
    from src.ascension.shop_offers import Offer

    async def work():
        env = Env(tmp_path / "db", offers=FixedOffers(Offer(1, "sentinel", "unique", 2)))
        try:
            await env.start_player()
            await env.give(insignia=100000)
            async with env.repo.transaction() as tx:
                await tx.add_battle(battle_record())
            with pytest.raises(BattleInProgress):
                await env.shop.buy_offer("ann", env.key(), env.offers.rotation_at(env.clock.now()), 1)
            async with env.repo.transaction() as tx:
                assert await tx.get_squad("ann") == ("guardian",)
                assert await tx.get_ascended("ann", "sentinel") is None
                assert (await tx.get_player("ann")).insignia == 100000
        finally:
            await env.close()

    run(work())
