import pytest

from src.brain.files import BrainFiles
from src.brain.limits import LongTermLimits, StackLimits
from src.brain.proposals import BrainProposals
from src.brain.stack import StackStore
from src.mcp_tools.proposal_tools import ProposalTools
from src.mcp_tools.scope import Scope

SCOPE = Scope("u-1", "chat-1")


@pytest.fixture
def world(tmp_path, db_gateway):
    files = BrainFiles(tmp_path / "brain", LongTermLimits(max_record_chars=300), refresh_seconds=0.0)
    stacks = StackStore(db_gateway, StackLimits())
    proposals = BrainProposals(db_gateway, files, stacks)
    return ProposalTools(proposals), proposals, files, stacks


async def test_a_proposal_waits_for_the_user_and_saves_nothing(world):
    tools, proposals, files, stacks = world
    item = await stacks.add("u-1", "chat-1", "likes green tea")
    answer = await tools.propose(SCOPE, "Tea habits", "The user likes green tea.", [item["id"]], "drinks", ["tea"])
    assert answer["ok"] is True and answer["proposal"]["title"] == "Tea habits"
    assert "nothing is saved" in answer["message"].lower() and "Tea habits" not in answer["message"]
    assert await files.list("u-1") == []
    assert len(await proposals.pending("u-1")) == 1


async def test_the_same_proposal_says_it_is_already_waiting(world):
    tools, _, _, _ = world
    await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    again = await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    assert again["ok"] is True and "already waiting" in again["message"].lower()


async def test_refusals_are_results_not_errors(world):
    tools, proposals, _, _ = world
    for args in [(" ", "x", None, "", None), ("T", "x" * 301, None, "", None), ("T", "x", [99], "", None), ("T", "x", None, "../etc", None)]:
        refused = await tools.propose(SCOPE, *args)
        assert refused["ok"] is False and refused["message"] and "xxxxxxxxxx" not in refused["message"]
    await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    await proposals.decline("u-1", (await proposals.pending("u-1"))[0]["id"])
    declined = await tools.propose(SCOPE, "Tea", "likes tea", None, "", None)
    assert declined["ok"] is False and "do not propose it again" in declined["message"].lower()
