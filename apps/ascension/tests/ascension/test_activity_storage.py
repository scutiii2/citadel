from dataclasses import replace

from src.ascension.records import ActivityContext, ExpeditionRecord
from src.ascension.repository import SqliteAscendedRepository
from tests.ascension.env import run


def test_activity_and_expedition_storage(tmp_path):
    async def scenario():
        from tests.ascension.helpers import battle_record
        repo = SqliteAscendedRepository(tmp_path / 'game.sqlite')
        async with repo.transaction() as tx:
            battle = replace(battle_record(), activity=ActivityContext(kind='hunt', difficulty_id='frontier', overall=720, reward_multiplier=.8))
            await tx.add_battle(battle)
            assert (await tx.get_battle(battle.owner, battle.id)).activity == battle.activity
            assert await tx.mark_trial_clear('ann', 'enchant', 1)
            assert not await tx.mark_trial_clear('ann', 'enchant', 1)
            assert await tx.trial_clears('ann', 'enchant') == {1}
            expedition = ExpeditionRecord('x1', 'ann', 'guardian', 0, 7200, 2, 200, 50)
            await tx.add_expedition(expedition)
            assert await tx.unclaimed_expedition('ann') == expedition
            assert await tx.get_expedition('bob', 'x1') is None
            await tx.claim_expedition('ann', 'x1', 7200, {'xp': 200})
            assert await tx.unclaimed_expedition('ann') is None
            assert (await tx.get_expedition('ann', 'x1')).receipt == {'xp': 200}
        await repo.close()
    run(scenario())


def test_v7_database_migration_preserves_legacy_battle(tmp_path):
    import json
    import sqlite3
    from src.ascension.repository import SCHEMA, ACTIVITY_SCHEMA
    from tests.ascension.helpers import battle_record
    path = tmp_path / 'old.sqlite'
    battle = battle_record()
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.removesuffix(ACTIVITY_SCHEMA))
    conn.execute('PRAGMA user_version=7')
    conn.execute('INSERT INTO players VALUES (?, ?, ?, ?)', ('ann', 123, None, 1))
    conn.execute('INSERT INTO battles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                 (battle.id, battle.owner, battle.encounter_id, battle.status, battle.phase, battle.mode, battle.revision,
                  json.dumps(battle.setup.to_dict()), json.dumps(battle.state.to_dict()),
                  json.dumps([p.to_dict() for p in battle.player_personalities]), json.dumps([p.to_dict() for p in battle.wild_personalities]),
                  None, battle.rng_seed, battle.rng_counter, None, None, battle.created_at, battle.updated_at))
    conn.commit(); conn.close()
    async def scenario():
        repo = SqliteAscendedRepository(path)
        async with repo.transaction() as tx:
            resumed = await tx.active_battle('ann')
            assert resumed.setup == battle.setup and resumed.state == battle.state
            assert resumed.activity.kind == 'legacy' and resumed.activity.reward_multiplier == 1
            assert (await tx.get_player('ann')).insignia == 123
        await repo.close()
    run(scenario())
