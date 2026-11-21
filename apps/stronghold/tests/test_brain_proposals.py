import pytest

from src.brain.files import BrainError, BrainFiles
from src.brain.limits import LongTermLimits, StackLimits
from src.brain.proposals import MAX_PENDING, BrainProposals
from src.brain.stack import StackStore
from src.document_store import DbGatewayUnavailable

OWNER, OTHER, CHAT = "u-1", "u-2", "chat-1"


@pytest.fixture
def world(tmp_path, db_gateway):
    files = BrainFiles(tmp_path / "brain", LongTermLimits(max_record_chars=300, max_files=2), refresh_seconds=0.0)
    stacks = StackStore(db_gateway, StackLimits())
    return BrainProposals(db_gateway, files, stacks), files, stacks


async def test_propose_stores_a_pending_proposal_without_touching_files(world):
    proposals, files, stacks = world
    item = await stacks.add(OWNER, CHAT, "likes green tea")
    made, waiting = await proposals.propose(OWNER, CHAT, " Tea  habits ", "The user likes green tea.", [item["id"]], "drinks", ["Tea"])
    assert waiting is False
    assert (made["title"], made["folder"], made["tags"], made["status"]) == ("Tea habits", "drinks", ["tea"], "pending")
    assert made["item_ids"] == [item["id"]] and made["chat_id"] == CHAT and "body" not in made
    assert await files.list(OWNER) == []
    assert [p["id"] for p in await proposals.pending(OWNER)] == [made["id"]]
    assert await proposals.pending(OTHER) == []


async def test_the_detail_has_the_text_and_the_untrusted_notice(world):
    proposals, _, _ = world
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "The user likes green tea.", [])
    detail = await proposals.get(OWNER, made["id"])
    assert detail["body"] == "The user likes green tea." and "agent wrote" in detail["notice"].lower()
    with pytest.raises(BrainError) as gone:
        await proposals.get(OTHER, made["id"])
    assert gone.value.status == 404


async def test_a_bad_proposal_is_refused_without_echoing_the_text(world):
    proposals, _, stacks = world
    for args in [(" ", "body", []), ("Title", " ", []), ("Title", "x" * 301, []), ("Title", "body", [99]),
                 ("Title", "body", list(range(1, 22)))]:
        with pytest.raises(BrainError) as refused:
            await proposals.propose(OWNER, CHAT, *args)
        assert refused.value.status == 422 and "x" * 20 not in str(refused.value)
    with pytest.raises(BrainError):
        await proposals.propose(OWNER, CHAT, "Title", "body", [], folder="../etc")


async def test_the_same_proposal_is_not_stored_twice(world):
    proposals, _, _ = world
    first, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    again, waiting = await proposals.propose(OWNER, CHAT, "tea", "likes tea", [])
    assert waiting is False  # the title differs in case, so the fingerprint differs
    same, waiting = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    assert waiting is True and same["id"] == first["id"]
    assert len(await proposals.pending(OWNER)) == 2


async def test_the_pending_cap(world):
    proposals, _, _ = world
    for number in range(MAX_PENDING):
        await proposals.propose(OWNER, CHAT, f"Title {number}", "body", [])
    with pytest.raises(BrainError) as full:
        await proposals.propose(OWNER, CHAT, "One more", "body", [])
    assert full.value.status == 409 and str(MAX_PENDING) in str(full.value)
    assert (await proposals.propose(OTHER, CHAT, "Mine", "body", []))[1] is False


async def test_accept_creates_an_agent_file_and_can_remove_the_items(world):
    proposals, files, stacks = world
    first = await stacks.add(OWNER, CHAT, "likes green tea")
    keep = await stacks.add(OWNER, CHAT, "uses metric units")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "The user likes green tea.", [first["id"]], "drinks")
    done = await proposals.accept(OWNER, made["id"], title="Green tea", folder="likes", remove_items=True)
    assert done["status"] == "accepted" and done["removed"] == 1
    record = await files.get(OWNER, done["result_id"])
    assert (record.title, record.folder, record.body, record.source, record.last_editor) == (
        "Green tea", "likes", "The user likes green tea.", "automatic", "agent")
    assert [i["id"] for i in (await stacks.view(OWNER, CHAT))["items"]] == [keep["id"]]
    assert await proposals.pending(OWNER) == []
    with pytest.raises(BrainError) as decided:
        await proposals.accept(OWNER, made["id"])
    assert decided.value.status == 409 and "already decided" in str(decided.value)


async def test_accept_keeps_the_items_unless_asked(world):
    proposals, files, stacks = world
    item = await stacks.add(OWNER, CHAT, "likes green tea")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [item["id"]])
    done = await proposals.accept(OWNER, made["id"])
    assert done["removed"] == 0 and (await stacks.view(OWNER, CHAT))["used"] == 1
    assert (await files.get(OWNER, done["result_id"])).folder == ""


async def test_a_refused_accept_leaves_the_proposal_pending(world):
    proposals, files, _ = world
    await files.create(OWNER, title="a", body="a")
    await files.create(OWNER, title="b", body="b")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    with pytest.raises(BrainError) as full:
        await proposals.accept(OWNER, made["id"])
    assert full.value.status == 409
    assert [p["id"] for p in await proposals.pending(OWNER)] == [made["id"]]


async def test_a_gone_stack_does_not_stop_a_kept_proposal(world):
    proposals, files, stacks = world
    item = await stacks.add(OWNER, CHAT, "likes tea")
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [item["id"]])
    await stacks.remove(OWNER, CHAT, item["id"])
    done = await proposals.accept(OWNER, made["id"], remove_items=True)
    assert done["status"] == "accepted" and done["removed"] == 0


async def test_decline_clears_the_text_and_blocks_the_same_proposal(world):
    proposals, _, _ = world
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    assert (await proposals.decline(OWNER, made["id"]))["status"] == "declined"
    assert (await proposals.get(OWNER, made["id"]))["body"] == ""
    with pytest.raises(BrainError) as again:
        await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    assert again.value.status == 409 and "declined" in str(again.value).lower()
    with pytest.raises(BrainError) as other:
        await proposals.decline(OTHER, made["id"])
    assert other.value.status == 404


async def test_purge_deletes_only_that_account(world):
    proposals, _, _ = world
    await proposals.propose(OWNER, CHAT, "Tea", "likes tea", [])
    mine, _ = await proposals.propose(OTHER, CHAT, "Tea", "likes tea", [])
    await proposals.purge(OWNER)
    assert await proposals.pending(OWNER) == []
    assert [p["id"] for p in await proposals.pending(OTHER)] == [mine["id"]]


async def test_decided_history_cannot_hide_waiting_suggestions_or_duplicates(world):
    proposals, _, _ = world
    first, _ = await proposals.propose(OWNER, CHAT, "Old suggestion", "Old text.", [])
    await proposals.decline(OWNER, first["id"])
    for number in range(205):
        made, _ = await proposals.propose(OWNER, CHAT, f"Decided {number}", "Body.", [])
        await proposals.decline(OWNER, made["id"])

    for number in range(MAX_PENDING):
        await proposals.propose(OWNER, CHAT, f"Waiting {number}", "Body.", [])
    assert [row["title"] for row in await proposals.pending(OWNER)] == [
        f"Waiting {number}" for number in reversed(range(MAX_PENDING))
    ]
    with pytest.raises(BrainError, match="Do not propose it again"):
        await proposals.propose(OWNER, CHAT, "Old suggestion", "Old text.", [])
    with pytest.raises(BrainError, match="20 suggestions waiting"):
        await proposals.propose(OWNER, CHAT, "Too many", "Body.", [])


async def test_a_keep_retried_after_a_storage_error_creates_only_one_file(world, db_gateway, monkeypatch):
    proposals, files, _ = world
    made, _ = await proposals.propose(OWNER, CHAT, "Tea", "Likes tea.", [])

    async def unavailable(*_args):
        raise DbGatewayUnavailable("example storage error")

    with monkeypatch.context() as temporary:
        temporary.setattr(db_gateway, "put", unavailable)
        with pytest.raises(DbGatewayUnavailable):
            await proposals.accept(OWNER, made["id"])
    assert [row["id"] for row in await proposals.pending(OWNER)] == [made["id"]]
    assert len(await files.list(OWNER)) == 1
    done = await proposals.accept(OWNER, made["id"])
    assert [record.id for record in await files.list(OWNER)] == [done["result_id"]]
    assert await proposals.pending(OWNER) == []
    with pytest.raises(BrainError, match="Do not propose it again"):
        await proposals.propose(OWNER, CHAT, "Tea", "Likes tea.", [])
