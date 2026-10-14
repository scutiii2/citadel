import pytest
from src.ascension.errors import Conflict
from src.ascension.expeditions import ExpeditionService
from src.ascension.squad import SquadService
from tests.ascension.env import Env, run


def test_dispatched_species_mutations_are_locked(tmp_path):
    async def scenario():
        env = Env(tmp_path / 'game.sqlite')
        await env.start_player()
        expedition = ExpeditionService(env.repo, env.writer, env.catalog, env.progression, env.clock)
        await expedition.start('ann', env.key(), 'guardian', 2)
        assert (await env.trees.view('ann', 'guardian'))['ascended_id'] == 'guardian'
        calls = [
            lambda: SquadService(env.repo, env.writer, env.catalog).put('ann', env.key(), ['guardian']),
            lambda: env.upgrades.add_star('ann', env.key(), 'guardian'),
            lambda: env.upgrades.raise_tier('ann', env.key(), 'guardian'),
            lambda: env.collection.set_default_preset('ann', env.key(), 'guardian', 2),
            lambda: env.collection.put_preset('ann', env.key(), 'guardian', 1, []),
            lambda: env.trees.set_loadout('ann', env.key(), 'guardian', {}),
        ]
        for call in calls:
            with pytest.raises(Conflict, match='expedition'):
                await call()
        async with env.repo.transaction() as tx:
            await SquadService.auto_equip(tx, 'ann', 'guardian', 5)
            assert await tx.get_squad('ann') == ()
        await env.close()
    run(scenario())


@pytest.mark.parametrize('competitor', ['battle','squad','upgrade'])
def test_departure_races_leave_no_dispatched_squad_or_battle(tmp_path, competitor):
    import asyncio
    from src.ascension.records import AscendedRecord
    async def scenario():
        env=Env(tmp_path/'game.sqlite')
        await env.start_player()
        await env.give(guardian=AscendedRecord('ann','guardian',3,1,0,tier_id='common'))
        await env.give_essence('common',10)
        service=ExpeditionService(env.repo,env.writer,env.catalog,env.progression,env.clock)
        preview=await env.encounters.roll('ann',env.key())
        if competitor=='battle':
            other=env.coordinator().start('ann',env.key(),encounter_id=preview['id'],ascended_id='guardian',preset_slot=1,mode='manual',emblem_limit=None)
        elif competitor=='squad':
            other=SquadService(env.repo,env.writer,env.catalog).put('ann',env.key(),['guardian'])
        else:
            other=env.upgrades.add_star('ann',env.key(),'guardian')
        results=await asyncio.gather(service.start('ann',env.key(),'guardian',2),other,return_exceptions=True)
        assert all(isinstance(result,(dict,Conflict)) for result in results)
        async with env.repo.transaction() as tx:
            expedition=await tx.unclaimed_expedition('ann')
            if expedition:
                assert 'guardian' not in await tx.get_squad('ann')
                assert await tx.active_battle('ann') is None
        await env.close()
    run(scenario())


def test_capturing_a_dispatched_duplicate_preserves_lock_and_owned_state(tmp_path):
    from dataclasses import replace
    from src.ascension.records import AscendedRecord
    from src.ascension.squad import SquadService
    from tests.ascension.helpers import battle_record
    async def scenario():
        env=Env(tmp_path/'game.sqlite')
        await env.start_player()
        await env.give(striker=AscendedRecord('ann','striker',0,1,0,tier_id='common'))
        service=ExpeditionService(env.repo,env.writer,env.catalog,env.progression,env.clock)
        await service.start('ann',env.key(),'guardian',2)
        await SquadService(env.repo,env.writer,env.catalog).put('ann',env.key(),['striker'])
        record=battle_record()
        record=replace(record,setup=replace(record.setup,player=env.engine.build_fighter('player','striker','common',1),wild=env.engine.build_fighter('wild','guardian','common',1)))
        async with env.repo.transaction() as tx:
            before=await tx.get_ascended('ann','guardian')
            result=await env.progression.apply_terminal(tx,record,'captured',env.rng)
            after=await tx.get_ascended('ann','guardian')
            assert result['copies_granted']==1 and after.copies==before.copies+1
            assert (after.level,after.xp,after.stars,after.tier_id)==(before.level,before.xp,before.stars,before.tier_id)
            assert await tx.get_squad('ann')==('striker',)
            with pytest.raises(Conflict):
                from src.ascension.expeditions import require_available
                await require_available(tx,'ann','guardian')
        await env.close()
    run(scenario())


def test_buying_a_dispatched_duplicate_preserves_lock_and_progression(tmp_path):
    from src.ascension.shop_offers import Offer
    from tests.ascension.helpers import FixedOffers
    async def scenario():
        env=Env(tmp_path/'game.sqlite',offers=FixedOffers(Offer(0,'guardian','common',3)))
        await env.start_player()
        await env.give(insignia=1000)
        service=ExpeditionService(env.repo,env.writer,env.catalog,env.progression,env.clock)
        await service.start('ann',env.key(),'guardian',2)
        bought=await env.shop.buy_offer('ann',env.key(),env.offers.rotation_at(env.clock.now()),0)
        async with env.repo.transaction() as tx:
            owned=await tx.get_ascended('ann','guardian')
            assert owned.copies==bought['copies_granted']
            assert (owned.level,owned.xp,owned.stars)==(1,0,0)
            assert await tx.get_squad('ann')==()
            assert (await tx.unclaimed_expedition('ann')).ascended_id=='guardian'
        await env.close()
    run(scenario())
