import pytest

from src.brain.files import BrainError, BrainFiles
from src.brain.global_brain import GLOBAL_UID, GlobalBrain
from src.brain.limits import LongTermLimits, SharingLimits, StackLimits
from src.brain.shares import BLOCKS, SHARES, BrainShares
from src.brain.skills import SkillFiles
from src.brain.stack import StackStore

A, B, C = "u-a", "u-b", "u-c"


@pytest.fixture
def world(tmp_path, db_gateway):
    brain = BrainFiles(tmp_path / "brain", LongTermLimits(), refresh_seconds=0.0)
    stacks = StackStore(db_gateway, StackLimits())
    shares = BrainShares(db_gateway, brain, SkillFiles(brain), stacks, GlobalBrain(tmp_path / "brain", LongTermLimits()), SharingLimits())
    return type("World", (), {"brain": brain, "skills": SkillFiles(brain), "stacks": stacks, "shares": shares, "db": db_gateway,
                              "global_brain": shares._global})()


async def refused(coro, status):
    with pytest.raises(BrainError) as error:
        await coro
    assert error.value.status == status
    return str(error.value)


async def share_file(world, body="Likes [diet](private/diet.md) and [site](https://a.test).", **extra):
    made = await world.brain.create(A, title="Diet", body=body, tags=["food"])
    given = await world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=B, recipient_name="bo", **extra)
    return made, given


async def test_a_file_share_is_a_pending_sanitised_snapshot_the_recipient_accepts(world):
    made, given = await share_file(world)
    assert (given["status"], given["kind"], given["sender"], given["recipient"], given["title"]) == ("pending", "file", "alice", "bo", "Diet")
    await world.brain.update(A, made.id, body="changed later")  # the snapshot is frozen
    assert [s["id"] for s in await world.shares.inbox(B)] == [given["id"]]
    assert await world.shares.inbox(A) == [] and await world.shares.inbox(C) == []
    seen = await world.shares.get(B, given["id"])
    assert seen["body"] == "Likes diet and [site](https://a.test)." and "untrusted" in seen["notice"].lower()
    done = await world.shares.accept(B, given["id"])
    assert done["status"] == "accepted" and done["result_id"]
    record = await world.brain.get(B, done["result_id"])
    assert (record.source, record.shared_from, record.folder, record.tags, record.title) == ("shared", "alice", "shared", (), "Diet")
    assert record.body == "Likes diet and [site](https://a.test)."
    await refused(world.shares.accept(B, given["id"]), 409)
    assert await world.shares.inbox(B) == []


async def test_the_recipient_picks_title_and_folder_and_only_the_recipient_decides(world):
    _, given = await share_file(world)
    await refused(world.shares.accept(C, given["id"]), 404)
    await refused(world.shares.accept(A, given["id"]), 404)
    await refused(world.shares.decline(C, given["id"]), 404)
    done = await world.shares.accept(B, given["id"], title="Their diet", folder="friends")
    record = await world.brain.get(B, done["result_id"])
    assert (record.title, record.folder) == ("Their diet", "friends")


async def test_decline_and_revoke_clear_the_text(world):
    _, first = await share_file(world)
    declined = await world.shares.decline(B, first["id"])
    assert declined["status"] == "declined"
    doc = await world.db.get(SHARES, first["id"])
    assert doc["body"] == "" and doc["skill"] is None
    made = await world.brain.create(A, title="Other", body="secret text")
    second = await world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=B, recipient_name="bo")
    await refused(world.shares.revoke(B, second["id"]), 404)
    assert (await world.shares.revoke(A, second["id"]))["status"] == "revoked"
    assert (await world.db.get(SHARES, second["id"]))["body"] == ""
    await refused(world.shares.accept(B, second["id"]), 409)
    assert sorted(s["status"] for s in await world.shares.sent(A)) == ["declined", "revoked"]


async def test_a_section_a_skill_and_a_stack_item_can_be_shared(world):
    body = "intro\n# Setup\nstep one\n# Usage\nrun it"
    made = await world.brain.create(A, title="Guide", body=body)
    section = await world.shares.create(A, "alice", "section", {"file_id": made.id, "heading": "Setup"}, recipient_uid=B, recipient_name="bo")
    assert section["title"] == "Guide: Setup"
    assert (await world.shares.get(B, section["id"]))["body"] == "# Setup\nstep one"
    await refused(world.shares.create(A, "alice", "section", {"file_id": made.id, "heading": "Nope"}, recipient_uid=B, recipient_name="bo"), 404)

    skill, _ = await world.skills.propose(A, "Restart an app", "hung", "stop it, then start it", "tool_srv_stopApp")
    given = await world.shares.create(A, "alice", "skill", {"skill_id": skill.id}, recipient_uid=B, recipient_name="bo")
    done = await world.shares.accept(B, given["id"])
    imported = next(s for s in await world.skills.list(B) if s.id == int(done["result_id"]))
    assert (imported.status, imported.successes, imported.failures, imported.shared_from) == ("proposed", 0, 0, "alice")
    again = await world.shares.create(A, "alice", "skill", {"skill_id": skill.id}, recipient_uid=B, recipient_name="bo")
    await refused(world.shares.accept(B, again["id"]), 409)
    renamed = await world.shares.accept(B, again["id"], title="Restart (alice)")
    assert renamed["status"] == "accepted"

    item = await world.stacks.add(A, "chat1", "I live in Paris")
    given = await world.shares.create(A, "alice", "stack_item", {"chat_id": "chat1", "item_id": item["id"]}, recipient_uid=B, recipient_name="bo")
    done = await world.shares.accept(B, given["id"])
    assert (await world.brain.get(B, done["result_id"])).body == "I live in Paris"
    await refused(world.shares.create(A, "alice", "stack_item", {"chat_id": "chat1", "item_id": 99}, recipient_uid=B, recipient_name="bo"), 404)
    await refused(world.shares.create(B, "bo", "file", {"file_id": "0" * 32}, recipient_uid=A, recipient_name="alice"), 404)


async def test_blocking_hides_the_recipient_and_declines_what_is_waiting(world):
    made, given = await share_file(world)
    await world.shares.block(B, A, "alice")
    assert (await world.db.get(SHARES, given["id"]))["status"] == "declined"
    assert [b["username"] for b in await world.shares.blocks(B)] == ["alice"]
    message = await refused(world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=B, recipient_name="bo"), 404)
    assert message == "No such recipient."
    await refused(world.shares.block(B, B, "bo"), 422)
    await world.shares.unblock(B, A)
    await world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=B, recipient_name="bo")
    await refused(world.shares.unblock(B, A), 404)


async def test_limits_duplicates_and_self_shares(world, db_gateway):
    made, _ = await share_file(world)
    await refused(world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=B, recipient_name="bo"), 409)  # duplicate
    await refused(world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=A, recipient_name="alice"), 404)
    world.shares.limits = SharingLimits(max_pending_sent=1)
    other = await world.brain.create(A, title="Two", body="second")
    await refused(world.shares.create(A, "alice", "file", {"file_id": other.id}, recipient_uid=C, recipient_name="cy"), 409)
    world.shares.limits = SharingLimits(max_inbox=1)
    await refused(world.shares.create(A, "alice", "file", {"file_id": other.id}, recipient_uid=B, recipient_name="bo"), 409)
    world.shares.limits = SharingLimits(max_share_chars=200)
    big = await world.brain.create(A, title="Big", body="x" * 300)
    await refused(world.shares.create(A, "alice", "file", {"file_id": big.id}, recipient_uid=C, recipient_name="cy"), 422)


async def test_global_shares_wait_for_a_reviewer(world):
    made = await world.brain.create(A, title="Diet", body="A note to review")
    given = await world.shares.create(A, "alice", "file", {"file_id": made.id}, recipient_uid=None, recipient_name="")
    assert given["recipient"] == "global brain" and given["status"] == "pending"
    assert await world.shares.inbox(B) == []
    assert [s["id"] for s in await world.shares.queue()] == [given["id"]]
    await refused(world.shares.accept(B, given["id"]), 404)  # a normal recipient cannot take a global share
    assert (await world.shares.get(C, given["id"], reviewer=True))["body"]
    await refused(world.shares.get(C, given["id"]), 404)
    done = await world.shares.review(given["id"], True, title="House diet", folder="policy")
    record = await world.global_brain.files.get(GLOBAL_UID, done["result_id"])
    assert (record.title, record.folder, record.source, record.shared_from) == ("House diet", "policy", "shared", "alice")
    assert await world.shares.queue() == []

    skill, _ = await world.skills.propose(A, "Rotate logs", "big logs", "rotate them", "")
    second = await world.shares.create(A, "alice", "skill", {"skill_id": skill.id}, recipient_uid=None, recipient_name="")
    rejected = await world.shares.review(second["id"], False)
    assert rejected["status"] == "rejected" and (await world.db.get(SHARES, second["id"]))["skill"] is None
    third = await world.shares.create(A, "alice", "skill", {"skill_id": skill.id}, recipient_uid=None, recipient_name="")
    done = await world.shares.review(third["id"], True)
    assert (await world.global_brain.skills.list(GLOBAL_UID))[0].status == "proposed" and done["status"] == "accepted"


async def test_a_full_brain_leaves_the_share_pending(world):
    _, given = await share_file(world)
    world.brain.limits = LongTermLimits(max_files=1)
    await world.brain.create(B, title="Full", body="x")
    await refused(world.shares.accept(B, given["id"]), 409)
    assert (await world.shares.get(B, given["id"]))["status"] == "pending"


async def test_purge_removes_every_share_and_block_of_an_account(world):
    made, given = await share_file(world)
    await world.shares.block(C, A, "alice")
    await world.shares.purge(A)
    assert await world.db.get(SHARES, given["id"]) is None
    assert await world.shares.blocks(C) == []
    other, _ = await world.brain.create(B, title="Mine", body="m"), None
    await world.shares.create(B, "bo", "file", {"file_id": other.id}, recipient_uid=C, recipient_name="cy")
    await world.shares.purge(C)
    assert await world.shares.sent(B) == []
    assert await world.db.query(BLOCKS) == []


async def test_purge_continues_past_the_first_page(world):
    for index in range(205):
        share_id = f"{index:032x}"
        await world.db.put(SHARES, share_id, {"id": share_id, "sender_uid": A, "recipient_uid": B})
    await world.shares.purge(A)
    assert await world.db.query(SHARES) == []


async def test_inbox_cap_above_one_page_is_enforced(world):
    world.shares.limits = SharingLimits(max_inbox=201)
    for index in range(201):
        share_id = f"{index:032x}"
        await world.db.put(SHARES, share_id, {"id": share_id, "recipient_uid": B, "status": "pending"})
    await refused(share_file(world), 409)
