from __future__ import annotations

from pathlib import Path

import pytest

from src.services.forge.groups import (
    MAX_GROUPS_PER_ACCOUNT,
    MAX_MEMBERS,
    AlreadyMember,
    GroupLimitError,
    GroupNotFound,
    GroupService,
    InvalidGroup,
    MemberLimitError,
    NotAMember,
    WorkerNotEligible,
)
from src.services.forge.plans import PlanPolicyRegistry
from src.services.forge.workers import WorkerNotFound
from tests.forge_support import run


def service(session, account_id: int = 1) -> GroupService:
    return GroupService(session, account_id, PlanPolicyRegistry(session))


def test_create_list_update_and_delete(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            groups = service(session)
            first = await groups.create("  Build   site ")
            second = await groups.create("Docs", mode="plan")
            assert (first.title, first.mode, first.relay) == ("Build site", "ask", False)
            assert [g.id for g in await groups.list()] == [second.id, first.id]  # newest first
            updated = await groups.update(first.id, title="Site", mode="accept_edits", relay=True)
            assert (updated.title, updated.mode, updated.relay) == ("Site", "accept_edits", True)
            await groups.delete(first.id)
            assert [g.id for g in await groups.list()] == [second.id]

    run(tmp_path, scenario)


def test_bad_titles_and_modes_are_refused(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            groups = service(session)
            with pytest.raises(InvalidGroup):
                await groups.create("   ")
            with pytest.raises(InvalidGroup):
                await groups.create("x" * 81)
            with pytest.raises(InvalidGroup):
                await groups.create("ok", mode="yolo")
            group = await groups.create("ok")
            with pytest.raises(InvalidGroup):
                await groups.update(group.id, mode="yolo")

    run(tmp_path, scenario)


def test_the_number_of_groups_is_limited(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            groups = service(session)
            for index in range(MAX_GROUPS_PER_ACCOUNT):
                await groups.create(f"g{index}")
            with pytest.raises(GroupLimitError):
                await groups.create("one more")

    run(tmp_path, scenario)


def test_another_accounts_group_looks_missing(tmp_path: Path) -> None:
    async def scenario(env):
        theirs = await env.add_group(account_id=2)
        async with env.database.sessions() as session:
            mine = service(session, 1)
            assert await mine.list() == []
            for call in (mine.get, mine.members, mine.delete):
                with pytest.raises(GroupNotFound):
                    await call(theirs.id)
            with pytest.raises(GroupNotFound):
                await mine.update(theirs.id, title="x")

    run(tmp_path, scenario)


def test_invite_needs_an_owned_eligible_worker_and_a_folder(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        mine = await env.add_worker(account_id=1, label="claude", plan="Max")
        theirs = await env.add_worker(account_id=2, label="claude", plan="Max")
        basic = await env.add_worker(account_id=1, label="basic", plan="Free")
        group = await env.add_group()
        async with env.database.sessions() as session:
            groups = service(session)
            member = await groups.invite(group.id, mine.id, "  C:/work/site ")
            assert (member.worker.label, member.folder, member.last_seq) == ("claude", "C:/work/site", 0)
            with pytest.raises(WorkerNotFound):
                await groups.invite(group.id, theirs.id, "C:/x")
            with pytest.raises(WorkerNotEligible) as refused:
                await groups.invite(group.id, basic.id, "C:/x")
            assert refused.value.reason == "Plan not eligible: Free"
            with pytest.raises(AlreadyMember):
                await groups.invite(group.id, mine.id, "C:/x")
            with pytest.raises(InvalidGroup):
                await groups.invite(group.id, basic.id, "   ")

    run(tmp_path, scenario)


def test_members_are_listed_and_removable(tmp_path: Path) -> None:
    async def scenario(env):
        a = await env.add_worker(label="a")
        b = await env.add_worker(label="b")
        group = await env.add_group(workers=[a, b])
        async with env.database.sessions() as session:
            groups = service(session)
            assert [m.worker.label for m in await groups.members(group.id)] == ["a", "b"]
            assert (await groups.member(group.id, a.id)).folder == "C:/work"
            await groups.remove_member(group.id, a.id)
            assert [m.worker.label for m in await groups.members(group.id)] == ["b"]
            with pytest.raises(NotAMember):
                await groups.member(group.id, a.id)
            with pytest.raises(NotAMember):
                await groups.remove_member(group.id, a.id)

    run(tmp_path, scenario)


def test_the_number_of_members_is_limited(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        group = await env.add_group()
        async with env.database.sessions() as session:
            groups = service(session)
            for index in range(MAX_MEMBERS):
                worker = await env.add_worker(label=f"w{index}")
                await groups.invite(group.id, worker.id, "C:/x")
            extra = await env.add_worker(label="extra")
            with pytest.raises(MemberLimitError):
                await groups.invite(group.id, extra.id, "C:/x")

    run(tmp_path, scenario)


def test_mark_seen_moves_the_workers_cursor_and_the_last_addressed(tmp_path: Path) -> None:
    async def scenario(env):
        worker = await env.add_worker()
        group = await env.add_group(workers=[worker])
        async with env.database.sessions() as session:
            groups = service(session)
            await groups.mark_seen(group.id, worker.id, 9)
            assert (await groups.member(group.id, worker.id)).last_seq == 9
            assert (await groups.get(group.id)).last_worker_id == worker.id

    run(tmp_path, scenario)


def test_a_member_can_be_moved_to_another_folder(tmp_path: Path) -> None:
    async def scenario(env):
        worker = await env.add_worker()
        group = await env.add_group(workers=[worker])
        async with env.database.sessions() as session:
            groups = service(session)
            moved = await groups.set_folder(group.id, worker.id, "  D:/other  ")
            assert moved.folder == "D:/other"
            assert (await groups.member(group.id, worker.id)).folder == "D:/other"
            with pytest.raises(InvalidGroup):
                await groups.set_folder(group.id, worker.id, "   ")
            with pytest.raises(NotAMember):
                await groups.set_folder(group.id, 999, "D:/x")
            with pytest.raises(GroupNotFound):
                await service(session, account_id=2).set_folder(group.id, worker.id, "D:/x")

    run(tmp_path, scenario)
