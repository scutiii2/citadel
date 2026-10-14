import pytest
from src.ascension.expeditions import ExpeditionService, require_available
from src.ascension.errors import Conflict, InvalidRequest
from tests.ascension.env import Env, run


def test_departure_claim_and_retry(tmp_path):
    async def scenario():
        env = Env(tmp_path / 'game.sqlite')
        await env.start_player()
        service = ExpeditionService(env.repo, env.writer, env.catalog, env.progression, env.clock)
        result = await service.start('ann', env.key(), 'guardian', 2)
        exp = result['expedition']
        assert exp['xp_reward'] == 200 and exp['insignia_reward'] == 50
        async with env.repo.transaction() as tx:
            assert await tx.get_squad('ann') == ()
            with pytest.raises(Conflict):
                await require_available(tx, 'ann', 'guardian')
        with pytest.raises(Conflict):
            await service.claim('ann', env.key(), exp['id'])
        env.clock.t = exp['ends_at']
        receipt = await service.claim('ann', env.key(), exp['id'])
        assert receipt['xp'] == 200 and receipt['insignia'] == 50
        assert await service.claim('ann', env.key(), exp['id']) == receipt
        async with env.repo.transaction() as tx:
            assert (await tx.get_player('ann')).insignia == 50
            assert await tx.get_squad('ann') == ()
            await require_available(tx, 'ann', 'guardian')
        await env.close()
    run(scenario())


@pytest.mark.parametrize('duration', [True, 0, 3, 2.5, -1])
def test_duration_validation(tmp_path, duration):
    async def scenario():
        env = Env(tmp_path / 'game.sqlite')
        service = ExpeditionService(env.repo, env.writer, env.catalog, env.progression, env.clock)
        with pytest.raises(InvalidRequest):
            await service.start('ann', env.key(), 'guardian', duration)
        await env.close()
    run(scenario())


def test_concurrent_departures_and_restart_claim(tmp_path):
    import asyncio
    from src.ascension.records import AscendedRecord
    async def scenario():
        path = tmp_path / 'game.sqlite'
        env = Env(path)
        await env.start_player()
        await env.give(striker=AscendedRecord('ann', 'striker', 0, 30, 0))
        service = ExpeditionService(env.repo, env.writer, env.catalog, env.progression, env.clock)
        results = await asyncio.gather(service.start('ann', env.key(), 'guardian', 8), service.start('ann', env.key(), 'striker', 8), return_exceptions=True)
        assert sum(isinstance(r, dict) for r in results) == 1
        expedition = next(r['expedition'] for r in results if isinstance(r, dict))
        await env.close()
        env = Env(path)
        env.clock.t = expedition['ends_at'] + 86400
        service = ExpeditionService(env.repo, env.writer, env.catalog, env.progression, env.clock)
        receipts = await asyncio.gather(service.claim('ann', env.key(), expedition['id']), service.claim('ann', env.key(), expedition['id']))
        assert receipts[0] == receipts[1] and receipts[0]['insignia'] == 200
        async with env.repo.transaction() as tx:
            assert (await tx.get_player('ann')).insignia == 200
        await env.close()
    run(scenario())
