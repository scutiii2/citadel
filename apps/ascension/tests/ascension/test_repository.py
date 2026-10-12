import asyncio
import sqlite3
from dataclasses import replace

import pytest

from src.ascension.errors import ActiveBattleExists, StaleBattle
from src.ascension.models import PersonalityInstance
from src.ascension.records import EncounterRecord, PersonalityRecord, PresetRecord, AscendedRecord
from src.ascension.repository import SqliteAscendedRepository
from tests.ascension.helpers import battle_record


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / ".data" / "ascension.sqlite3"


def test_players_and_wallet(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            assert await tx.get_player("ann") is None
            await tx.create_player("ann", 5.0)
            await tx.add_insignia("ann", 30)
            await tx.set_last_roll("ann", 9.0)
            player = await tx.get_player("ann")
        assert (player.insignia, player.last_roll_at, player.created_at) == (30, 9.0, 5.0)
        with pytest.raises(sqlite3.IntegrityError):
            async with repo.transaction() as tx:
                await tx.add_insignia("ann", -31)
        await repo.close()

    run(scenario())


def test_emblems_accumulate_and_cannot_go_negative(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.add_emblems("ann", "common", 5)
            await tx.add_emblems("ann", "common", -2)
            await tx.add_emblems("ann", "rare", 1)
            await tx.add_emblems("ann", "rare", -1)
            counts = await tx.emblem_counts("ann")
        assert counts == {"common": 3}
        with pytest.raises(sqlite3.IntegrityError):
            async with repo.transaction() as tx:
                await tx.add_emblems("ann", "common", -4)
        await repo.close()

    run(scenario())


def test_ascendeds_upsert_and_list(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.put_ascended(AscendedRecord("ann", "guardian", 0, 1, 0))
            await tx.put_ascended(AscendedRecord("ann", "guardian", 3, 4, 50, faint_until=99.0))
            await tx.put_ascended(AscendedRecord("bob", "guardian", 0, 1, 0))
            mine = await tx.list_ascendeds("ann")
            one = await tx.get_ascended("ann", "guardian")
            missing = await tx.get_ascended("ann", "scout")
        assert mine == [one] and one == AscendedRecord("ann", "guardian", 3, 4, 50, 99.0) and missing is None
        await repo.close()

    run(scenario())


def test_personalities_are_scoped_and_paginated(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            for i in range(5):
                await tx.add_personality(PersonalityRecord(f"p{i}", "ann", "guardian", "AGGRESSIVE", 1, float(i)))
            await tx.add_personality(PersonalityRecord("other", "ann", "scout", "COWARD", 2, 9.0))
            await tx.add_personality(PersonalityRecord("bobs", "bob", "guardian", "COWARD", 2, 9.0))
            first = await tx.list_personalities("ann", "guardian", 2, 0)
            second = await tx.list_personalities("ann", "guardian", 2, first[-1].seq)
            picked = await tx.get_personalities("ann", "guardian", ["p1", "other", "bobs", "p9"])
            nothing = await tx.get_personalities("ann", "guardian", [])
        assert [p.id for p in first] == ["p0", "p1"] and [p.id for p in second] == ["p2", "p3"]
        assert [p.id for p in picked] == ["p1"] and nothing == []
        assert first[0].instance() == PersonalityInstance("p0", "AGGRESSIVE", 1)
        await repo.close()

    run(scenario())


def test_presets_hold_five_slots(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.put_preset(PresetRecord("ann", "guardian", 1, ("a", "b")))
            await tx.put_preset(PresetRecord("ann", "guardian", 1, ("c",)))
            await tx.put_preset(PresetRecord("ann", "guardian", 2, ()))
            one = await tx.get_preset("ann", "guardian", 1)
            every = await tx.list_presets("ann", "guardian")
            nothing = await tx.get_preset("ann", "guardian", 3)
        assert one.instance_ids == ("c",) and [p.slot for p in every] == [1, 2] and nothing is None
        with pytest.raises(sqlite3.IntegrityError):
            async with repo.transaction() as tx:
                await tx.put_preset(PresetRecord("ann", "guardian", 6, ()))
        await repo.close()

    run(scenario())


def test_encounters_are_owner_safe_and_one_pending_at_a_time_is_read(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        wild = (PersonalityInstance("w1", "COWARD", 2),)
        async with repo.transaction() as tx:
            await tx.add_encounter(EncounterRecord("e1", "ann", "scout", "rare", 7, "pending", wild, 1.0))
            await tx.add_encounter(EncounterRecord("e2", "ann", "scout", "common", 3, "pending", wild, 2.0))
            newest = await tx.pending_encounter("ann")
            await tx.set_encounter_status("e2", "declined")
            after = await tx.pending_encounter("ann")
            mine = await tx.get_encounter("ann", "e1")
            foreign = await tx.get_encounter("bob", "e1")
        assert newest.id == "e2" and after.id == "e1" and mine.wild_personalities == wild and foreign is None
        await repo.close()

    run(scenario())


def test_battles_round_trip_and_enforce_one_active_per_owner(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        record = replace(battle_record(), pending={"wild_action": {"kind": "flee"}}, emblem_limit="rare")
        async with repo.transaction() as tx:
            await tx.add_battle(record)
            loaded = await tx.get_battle("ann", "b1")
            active = await tx.active_battle("ann")
            foreign = await tx.get_battle("bob", "b1")
        assert loaded == record and active == record and foreign is None
        with pytest.raises(ActiveBattleExists):
            async with repo.transaction() as tx:
                await tx.add_battle(battle_record(battle_id="b2", encounter_id="e2"))
        async with repo.transaction() as tx:
            await tx.save_battle(replace(record, status="terminal", phase="terminal", revision=2, result={"kind": "won"}), 1)
            await tx.add_battle(battle_record(battle_id="b3", encounter_id="e3"))  # the finished one no longer blocks
            assert (await tx.get_battle("ann", "b1")).result == {"kind": "won"}
            assert (await tx.active_battle("ann")).id == "b3"
        await repo.close()

    run(scenario())


def test_saving_with_a_stale_revision_is_rejected(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        record = battle_record()
        async with repo.transaction() as tx:
            await tx.add_battle(record)
            await tx.save_battle(replace(record, revision=2), 1)
        with pytest.raises(StaleBattle):
            async with repo.transaction() as tx:
                await tx.save_battle(replace(record, revision=2, rng_counter=9), 1)
        await repo.close()

    run(scenario())


def test_rounds_are_stored_and_replaced(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.add_round("b1", 1, {"mood": 0})
            await tx.add_round("b1", 1, {"mood": 1})
            rows = await tx._run("SELECT record FROM rounds WHERE battle_id = 'b1'", (), "all")
        assert [r["record"] for r in rows] == ['{"mood":1}']
        await repo.close()

    run(scenario())


def test_idempotency_records_are_unique_per_owner_and_key(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.put_idempotent("ann", "k1", "hash", {"ok": True}, 1.0)
            await tx.put_idempotent("bob", "k1", "other", {"ok": False}, 1.0)
            ann = await tx.get_idempotent("ann", "k1")
            missing = await tx.get_idempotent("ann", "k2")
        assert (ann.request_hash, ann.response) == ("hash", {"ok": True}) and missing is None
        with pytest.raises(sqlite3.IntegrityError):
            async with repo.transaction() as tx:
                await tx.put_idempotent("ann", "k1", "hash", {}, 2.0)
        await repo.close()

    run(scenario())


def test_a_failed_transaction_rolls_back_everything(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        with pytest.raises(RuntimeError):
            async with repo.transaction() as tx:
                await tx.create_player("ann", 1.0)
                await tx.add_emblems("ann", "common", 5)
                raise RuntimeError("boom")
        async with repo.transaction() as tx:
            assert await tx.get_player("ann") is None and await tx.emblem_counts("ann") == {}
        await repo.close()

    run(scenario())


def test_data_survives_a_restart(db_path):
    async def first():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)
            await tx.add_battle(battle_record())
        await repo.close()

    async def second():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            return await tx.get_player("ann"), await tx.active_battle("ann")

    run(first())
    player, battle = run(second())
    assert player.owner == "ann" and battle.id == "b1"


def test_transactions_run_one_at_a_time(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)

        async def bump():
            async with repo.transaction() as tx:
                before = (await tx.get_player("ann")).insignia
                await asyncio.sleep(0.01)
                await tx.add_insignia("ann", 1)
                return before

        seen = await asyncio.gather(*(bump() for _ in range(5)))
        async with repo.transaction() as tx:
            total = (await tx.get_player("ann")).insignia
        await repo.close()
        return sorted(seen), total

    seen, total = run(scenario())
    assert seen == [0, 1, 2, 3, 4] and total == 5


def test_unsupported_schema_version_is_refused(db_path):
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()

    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction():
            pass

    with pytest.raises(RuntimeError, match="schema version 99"):
        run(scenario())


def test_shop_purchases_are_counted_per_slot_and_pruned(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)
            await tx.add_shop_purchase("ann", 5, 0)
            await tx.add_shop_purchase("ann", 5, 0)
            await tx.add_shop_purchase("ann", 5, 2)
            await tx.add_shop_purchase("ann", 4, 1)
            before = await tx.shop_bought("ann", 5)
            await tx.prune_shop("ann", 5)
            old = await tx.shop_bought("ann", 4)
            await tx.delete_player_data("ann")
            gone = await tx.shop_bought("ann", 5)
        await repo.close()
        return before, old, gone

    before, old, gone = run(scenario())
    assert before == {0: 2, 2: 1} and old == {} and gone == {}


def test_a_version_2_database_is_upgraded_to_the_current_version(db_path):
    from src.ascension.repository import BASE_SCHEMA, SCHEMA_VERSION

    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(f"{BASE_SCHEMA} PRAGMA user_version = 2;")
    conn.execute("INSERT INTO players (owner, insignia, created_at) VALUES ('ann', 7, 1.0)")
    conn.commit()
    conn.close()

    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            player = await tx.get_player("ann")
            await tx.add_shop_purchase("ann", 1, 0)
            bought = await tx.shop_bought("ann", 1)
        await repo.close()
        return player, bought

    player, bought = run(scenario())
    check = sqlite3.connect(str(db_path))
    version = check.execute("PRAGMA user_version").fetchone()[0]
    check.close()
    assert player.insignia == 7 and bought == {0: 1} and version == SCHEMA_VERSION


def test_a_version_3_database_keeps_each_ascended_tier_and_spends_the_absorbed_copies(db_path):
    from src.ascension.repository import BASE_SCHEMA, SHOP_SCHEMA, SCHEMA_VERSION

    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(f"{BASE_SCHEMA} {SHOP_SCHEMA} PRAGMA user_version = 3;")
    conn.execute("INSERT INTO ascendeds (owner, ascended_id, copies, level, xp) VALUES ('ann', 'guardian', 12, 5, 0)")
    conn.execute("INSERT INTO ascendeds (owner, ascended_id, copies, level, xp) VALUES ('ann', 'scout', 3, 1, 0)")
    conn.commit()
    conn.close()

    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            guardian, scout = await tx.get_ascended("ann", "guardian"), await tx.get_ascended("ann", "scout")
            essences = await tx.essence_counts("ann")
        await repo.close()
        return guardian, scout, essences

    guardian, scout, essences = run(scenario())
    check = sqlite3.connect(str(db_path))
    version = check.execute("PRAGMA user_version").fetchone()[0]
    check.close()
    assert (guardian.tier_id, guardian.copies, guardian.stars) == ("rare", 0, 0)
    assert (scout.tier_id, scout.copies) == ("common", 0) and essences == {} and version == SCHEMA_VERSION


def test_essence_accumulates_per_tier_cannot_go_negative_and_is_wiped_with_the_player(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)
            await tx.add_essence("ann", "common", 5)
            await tx.add_essence("ann", "common", -2)
            await tx.add_essence("ann", "rare", 1)
            counts = await tx.essence_counts("ann")
        assert counts == {"common": 3, "rare": 1}
        with pytest.raises(sqlite3.IntegrityError):
            async with repo.transaction() as tx:
                await tx.add_essence("ann", "common", -4)
        async with repo.transaction() as tx:
            await tx.delete_player_data("ann")
            gone = await tx.essence_counts("ann")
        await repo.close()
        return gone

    assert run(scenario()) == {}


def test_tier_and_stars_round_trip(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.put_ascended(AscendedRecord("ann", "guardian", 2, 4, 50, tier_id="unique", stars=2))
            saved = await tx.get_ascended("ann", "guardian")
        await repo.close()
        return saved

    saved = run(scenario())
    assert (saved.tier_id, saved.stars, saved.copies) == ("unique", 2, 2)


def test_learned_nodes_and_loadouts_round_trip_and_reset(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)
            await tx.add_learned_node("ann", "guardian", "g_wall")
            await tx.add_learned_node("ann", "guardian", "g_wall")  # a repeat changes nothing
            await tx.add_learned_node("bob", "guardian", "g_other")
            await tx.put_loadout("ann", "guardian", {"a1": "g_wall", "p1": "g_skin"})
            await tx.put_loadout("ann", "guardian", {"a1": "g_a", "a2": "g_b"})  # replaces the old rows
            learned, loadout, none = (await tx.learned_nodes("ann", "guardian"), await tx.get_loadout("ann", "guardian"),
                                      await tx.get_loadout("ann", "scout"))
        async with repo.transaction() as tx:
            await tx.delete_player_data("ann")
            gone = (await tx.learned_nodes("ann", "guardian"), await tx.get_loadout("ann", "guardian"))
            bob = await tx.learned_nodes("bob", "guardian")
        await repo.close()
        return learned, loadout, none, gone, bob

    learned, loadout, none, gone, bob = run(scenario())
    assert learned == {"g_wall"} and loadout == {"a1": "g_a", "a2": "g_b"} and none == {}
    assert gone == (set(), {}) and bob == {"g_other"}


def test_a_version_4_database_gets_the_tree_tables(db_path):
    from src.ascension.repository import BASE_SCHEMA, SHOP_SCHEMA, STAR_MIGRATION, SCHEMA_VERSION

    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(f"{BASE_SCHEMA} {SHOP_SCHEMA} {STAR_MIGRATION} PRAGMA user_version = 4;")
    conn.execute("INSERT INTO ascendeds (owner, ascended_id, copies, level, xp, tier_id) VALUES ('ann', 'guardian', 2, 5, 0, 'rare')")
    conn.commit()
    conn.close()

    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            kept = await tx.get_ascended("ann", "guardian")
            await tx.add_learned_node("ann", "guardian", "g_wall")
            learned = await tx.learned_nodes("ann", "guardian")
        await repo.close()
        return kept, learned

    kept, learned = run(scenario())
    check = sqlite3.connect(str(db_path))
    version = check.execute("PRAGMA user_version").fetchone()[0]
    check.close()
    assert (kept.tier_id, kept.copies) == ("rare", 2) and learned == {"g_wall"} and version == SCHEMA_VERSION == 5
