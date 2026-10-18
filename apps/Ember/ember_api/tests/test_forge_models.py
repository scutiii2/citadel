from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select, text

from src.models import Account, ForgeGroup, ForgeGroupWorker, ForgeMessage, ForgeWorker
from tests.forge_support import run


def test_deleting_an_account_removes_its_workers_groups_members_and_messages(tmp_path: Path) -> None:
    async def scenario(env):
        worker = await env.add_worker(account_id=1)
        group = await env.add_group(account_id=1, workers=[worker])
        async with env.database.sessions() as session:
            session.add(ForgeMessage(group_id=group.id, seq=1, sender="user", kind="text", body={"text": "hi"}))
            await session.commit()
        async with env.database.sessions() as session:
            assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
            account = await session.get(Account, 1)
            await session.delete(account)
            await session.commit()
        async with env.database.sessions() as session:
            for model in (ForgeWorker, ForgeGroup, ForgeGroupWorker, ForgeMessage):
                assert await session.scalar(select(func.count()).select_from(model)) == 0

    run(tmp_path, scenario)


def test_a_message_body_round_trips_as_json(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group()
        async with env.database.sessions() as session:
            session.add(ForgeMessage(group_id=group.id, seq=1, sender="user", kind="text", body={"text": "ü", "n": [1, 2]}))
            await session.commit()
        async with env.database.sessions() as session:
            message = await session.scalar(select(ForgeMessage))
            assert message.body == {"text": "ü", "n": [1, 2]}

    run(tmp_path, scenario)
