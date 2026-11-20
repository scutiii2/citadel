import pytest

from src.brain.limits import StackLimits
from src.brain.stack import StackError, StackStore

OWNER, CHAT = "u-1", "chat-1"


@pytest.fixture
def stacks(db_gateway):
    return StackStore(db_gateway, StackLimits(max_items=4, max_item_chars=20, compact_item_chars=60, warn_ratio=0.75))


async def test_an_empty_stack_has_no_warning(stacks):
    view = await stacks.view(OWNER, CHAT)
    assert view == {"items": [], "used": 0, "limit": 4, "warn": False, "full": False}


async def test_add_cleans_the_text_and_numbers_items(stacks):
    first = await stacks.add(OWNER, CHAT, "  likes   tea ")
    second = await stacks.add(OWNER, CHAT, "uses metric")
    assert (first["id"], first["text"], first["source"], first["pinned"]) == (1, "likes tea", "agent", False)
    assert second["id"] == 2


async def test_the_same_text_is_not_stored_twice(stacks):
    first = await stacks.add(OWNER, CHAT, "likes tea")
    again = await stacks.add(OWNER, CHAT, "likes  TEA")
    assert again["id"] == first["id"]
    assert (await stacks.view(OWNER, CHAT))["used"] == 1


@pytest.mark.parametrize("text", ["", "   ", "x" * 21])
async def test_empty_or_long_text_is_refused(stacks, text):
    with pytest.raises(StackError) as error:
        await stacks.add(OWNER, CHAT, text)
    assert error.value.status == 422


async def test_overflow_drops_the_oldest_unpinned_item(stacks):
    for text in ("a", "b", "c", "d"):
        await stacks.add(OWNER, CHAT, text)
    await stacks.pin(OWNER, CHAT, 1, True)
    await stacks.add(OWNER, CHAT, "e")
    texts = [item["text"] for item in (await stacks.view(OWNER, CHAT))["items"]]
    assert texts == ["a", "c", "d", "e"]  # "b" was the oldest unpinned


async def test_a_stack_of_pinned_items_refuses_a_new_one(stacks):
    for index, text in enumerate(("a", "b", "c", "d"), start=1):
        await stacks.add(OWNER, CHAT, text, pinned=True)
    with pytest.raises(StackError) as error:
        await stacks.add(OWNER, CHAT, "e")
    assert error.value.status == 409


async def test_warn_starts_at_the_ratio_and_full_at_the_limit(stacks):
    for text in ("a", "b"):
        await stacks.add(OWNER, CHAT, text)
    assert (await stacks.view(OWNER, CHAT))["warn"] is False
    await stacks.add(OWNER, CHAT, "c")
    view = await stacks.view(OWNER, CHAT)
    assert (view["warn"], view["full"]) == (True, False)
    await stacks.add(OWNER, CHAT, "d")
    assert (await stacks.view(OWNER, CHAT))["full"] is True


async def test_remove_and_pin_need_an_existing_item(stacks):
    await stacks.add(OWNER, CHAT, "a")
    assert (await stacks.pin(OWNER, CHAT, 1, True))["pinned"] is True
    await stacks.remove(OWNER, CHAT, 1)
    for call in (stacks.remove(OWNER, CHAT, 1), stacks.pin(OWNER, CHAT, 1, False)):
        with pytest.raises(StackError) as error:
            await call
        assert error.value.status == 404


async def test_stacks_are_separate_per_chat_and_account(stacks):
    await stacks.add(OWNER, CHAT, "mine")
    assert (await stacks.view(OWNER, "chat-2"))["used"] == 0
    assert (await stacks.view("u-2", CHAT))["used"] == 0


async def test_compaction_replaces_only_the_named_unpinned_items(stacks):
    for text in ("a", "b", "c"):
        await stacks.add(OWNER, CHAT, text)
    await stacks.pin(OWNER, CHAT, 3, True)
    summary = await stacks.apply_compaction(OWNER, CHAT, [1, 2, 3], "a and b, short")
    view = await stacks.view(OWNER, CHAT)
    assert [i["text"] for i in view["items"]] == ["a and b, short", "c"]  # the pinned "c" was not replaced
    assert (summary["source"], summary["pinned"]) == ("compaction", False)


async def test_compaction_text_has_its_own_limit(stacks):
    await stacks.add(OWNER, CHAT, "a")
    with pytest.raises(StackError) as error:
        await stacks.apply_compaction(OWNER, CHAT, [1], "x" * 61)
    assert error.value.status == 422


async def test_delete_and_purge_remove_stacks(stacks, db_gateway):
    await stacks.add(OWNER, CHAT, "a")
    await stacks.add(OWNER, "chat-2", "b")
    await stacks.add("u-2", CHAT, "c")
    await stacks.delete(OWNER, CHAT)
    assert (await stacks.view(OWNER, CHAT))["used"] == 0
    await stacks.purge_owner(OWNER)
    assert (await stacks.view(OWNER, "chat-2"))["used"] == 0
    assert (await stacks.view("u-2", CHAT))["used"] == 1


async def test_chat_store_exists(db_gateway):
    from src.chats.store import ChatStore
    from src.shares.store import ShareStore
    chats = ChatStore(db_gateway, ShareStore(db_gateway))
    assert await chats.exists(OWNER, CHAT) is False
    await chats.put(OWNER, CHAT, "t", None, [])
    assert await chats.exists(OWNER, CHAT) is True
