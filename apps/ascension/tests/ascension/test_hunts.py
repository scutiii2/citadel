from dataclasses import replace

from src.ascension.records import ActivityContext, AscendedRecord
from tests.ascension.env import Env, run
from tests.ascension.helpers import battle_record


def test_hunt_roll_range_and_reward_penalty(tmp_path):
    async def scenario():
        env = Env(tmp_path / 'game.sqlite')
        await env.start_player()
        preview = await env.encounters.roll('ann', env.key(), 'frontier')
        assert 300 <= preview['overall'] <= 599
        assert preview['activity']['difficulty_id'] == 'frontier'
        battle = battle_record()
        battle = replace(battle, setup=replace(battle.setup, player=env.engine.build_fighter('player', 'guardian', 'common', 1),
                                              wild=env.engine.build_fighter('wild', 'scout', 'common', 10)),
                         activity=ActivityContext(kind='hunt', overall=720, reward_multiplier=1-121/599))
        async with env.repo.transaction() as tx:
            result = await env.progression.apply_terminal(tx, battle, 'won', env.rng)
        assert (result['xp'], result['insignia'], result['essence']) == (159, 79, 0)
        await env.close()
    run(scenario())
