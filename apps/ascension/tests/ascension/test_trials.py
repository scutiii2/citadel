import pytest

from src.ascension.errors import InvalidRequest
from tests.ascension.env import Env, run


def test_trial_eligibility_no_capture_and_first_clear(tmp_path):
    async def scenario():
        env = Env(tmp_path / 'game.sqlite')
        await env.start_player()
        coord = env.coordinator()
        with pytest.raises(InvalidRequest):
            await coord.start_trial('ann', env.key(), type_id='pure', stage=1, ascended_id='guardian', preset_slot=1, mode='manual')
        view = await coord.start_trial('ann', env.key(), type_id='enchant', stage=1, ascended_id='guardian', preset_slot=1, mode='autonomous')
        assert view['activity']['kind'] == 'trial'
        assert view['can_autonomous']
        assert not any(a['kind'] == 'catch' for a in view['actions'])
        async with env.repo.transaction() as tx:
            record = await tx.get_battle('ann', view['id'])
            result = await env.progression.apply_terminal(tx, record, 'won', env.rng)
            assert (result['xp'], result['insignia'], result['essence']) == (120, 60, 2)
            assert result['first_clear']
            replay = await env.progression.apply_terminal(tx, record, 'won', env.rng)
            assert not replay['first_clear'] and replay['xp'] == 60
        view = await coord.set_mode('ann', env.key(), view['id'], round=view['round'], revision=view['revision'], mode='manual', emblem_limit=None)
        with pytest.raises(InvalidRequest):
            await coord.submit_action('ann', env.key(), view['id'], round=view['round'], revision=view['revision'], action={'kind':'catch', 'emblem_tier':'common'})
        await env.close()
    run(scenario())


def test_multitype_trial_excludes_other_type_bench_xp(tmp_path):
    from src.ascension.records import AscendedRecord
    from src.ascension.squad import SquadService
    async def scenario():
        env=Env(tmp_path/'game.sqlite')
        await env.start_player()
        await env.give(twoychi=AscendedRecord('ann','twoychi',0,1,0,tier_id='unique'))
        await SquadService(env.repo,env.writer,env.catalog).put('ann',env.key(),['guardian','twoychi'])
        coord=env.coordinator()
        view=await coord.start_trial('ann',env.key(),type_id='divine',stage=1,ascended_id='twoychi',preset_slot=None,mode='manual')
        assert not view['can_autonomous']
        async with env.repo.transaction() as tx:
            record=await tx.get_battle('ann',view['id'])
            result=await env.progression.apply_terminal(tx,record,'won',env.rng)
            assert result['squad_xp']==[]
            assert (await tx.get_ascended('ann','guardian')).xp==0
        await env.close()
    run(scenario())
