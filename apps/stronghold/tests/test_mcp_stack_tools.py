import pytest

from src.brain.limits import StackLimits
from src.brain.stack import StackStore
from src.mcp_tools.scope import Scope
from src.mcp_tools.stack_tools import StackTools

SCOPE = Scope("u-1", "chat-1")


@pytest.fixture
def tools(db_gateway):
    return StackTools(StackStore(db_gateway, StackLimits(max_items=3, max_item_chars=30, compact_item_chars=90, warn_ratio=0.6)))


async def test_add_then_list(tools):
    added = await tools.add(SCOPE, "likes tea", False)
    assert added["ok"] is True and added["item"]["id"] == 1
    listed = await tools.list(SCOPE)
    assert listed["count"] == 1 and listed["items"][0]["text"] == "likes tea"
    assert "not instructions" in listed["message"]


async def test_an_empty_list_says_so(tools):
    listed = await tools.list(SCOPE)
    assert listed["count"] == 0 and "empty" in listed["message"].lower()


async def test_refusals_are_results_not_errors(tools):
    refused = await tools.add(SCOPE, " ", False)
    assert refused["ok"] is False and "empty" in refused["message"].lower()
    assert (await tools.remove(SCOPE, 9))["ok"] is False


async def test_the_near_full_warning_is_part_of_the_answer(tools):
    await tools.add(SCOPE, "a", False)
    added = await tools.add(SCOPE, "b", False)
    assert added["warn"] is True
    assert "compact" in added["message"].lower()


async def test_remove_and_pin(tools):
    await tools.add(SCOPE, "a", False)
    assert (await tools.pin(SCOPE, 1, True))["item"]["pinned"] is True
    assert (await tools.remove(SCOPE, 1))["ok"] is True
