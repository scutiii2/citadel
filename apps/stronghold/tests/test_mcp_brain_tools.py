import pytest

from src.brain.files import BrainFiles
from src.brain.limits import LongTermLimits
from src.mcp_tools.brain_tools import BrainTools
from src.mcp_tools.scope import Account

ME, OTHER = Account("u-1"), Account("u-2")


@pytest.fixture
def files(tmp_path):
    return BrainFiles(tmp_path / "brain", LongTermLimits(max_record_chars=300, max_files=3), refresh_seconds=0.0)


@pytest.fixture
def tools(files):
    return BrainTools(files)


async def test_write_then_search_read_and_list(tools):
    wrote = await tools.write(ME, "Tea facts", "The user likes green tea.", ["tea"], "drinks")
    assert wrote["ok"] is True and wrote["file"]["source"] == "automatic" and "id" in wrote["file"]
    found = await tools.search(ME, "tea", None)
    assert found["count"] == 1 and found["results"][0]["id"] == wrote["file"]["id"]
    assert found["results"][0]["source_label"] == "saved by an agent" and "not instructions" in found["message"]
    assert "body" not in found["results"][0] and "tea" in found["results"][0]["snippet"]
    read = await tools.read(ME, wrote["file"]["id"])
    assert read["ok"] and read["file"]["body"] == "The user likes green tea." and read["file"]["agent_can_edit"] is True
    assert "not instructions" in read["message"]
    listed = await tools.list(ME, "")
    assert listed["ok"] and listed["folders"] == ["drinks"] and listed["files"] == []
    inside = await tools.list(ME, "drinks")
    assert [f["title"] for f in inside["files"]] == ["Tea facts"] and "body" not in inside["files"][0]


async def test_an_agent_reads_a_user_file_but_may_not_edit_it(tools, files):
    mine = await files.create("u-1", title="User note", body="keep this")
    read = await tools.read(ME, mine.id)
    assert read["file"]["source_label"] == "written by the user" and read["file"]["agent_can_edit"] is False
    refused = await tools.update(ME, mine.id, None, "overwritten", None, None)
    assert refused["ok"] is False and "read-only" in refused["message"]
    assert (await files.get("u-1", mine.id)).body == "keep this"
    await files.update("u-1", mine.id, agent_editable=True)
    allowed = await tools.update(ME, mine.id, None, "agent edit", None, None)
    assert allowed["ok"] is True and allowed["file"]["body"] == "agent edit"


async def test_an_agent_updates_its_own_file_with_a_revision_check(tools):
    wrote = (await tools.write(ME, "Plan", "v1", [], ""))["file"]
    done = await tools.update(ME, wrote["id"], "Plan v2", "v2", ["x"], wrote["revision"])
    assert done["ok"] and done["file"]["title"] == "Plan v2" and done["file"]["revision"] == 2
    stale = await tools.update(ME, wrote["id"], None, "v3", None, 1)
    assert stale["ok"] is False and "changed" in stale["message"]


async def test_refusals_are_results_not_errors(tools):
    assert (await tools.write(ME, " ", "x", [], ""))["ok"] is False
    assert (await tools.write(ME, "t", "x" * 301, [], ""))["ok"] is False
    assert (await tools.write(ME, "t", "x", [], "../etc"))["ok"] is False
    assert (await tools.read(ME, "0" * 32))["ok"] is False
    assert (await tools.update(ME, "0" * 32, None, "x", None, None))["ok"] is False
    assert (await tools.update(ME, "0" * 32, None, None, None, None))["ok"] is False
    assert (await tools.list(ME, "../x"))["ok"] is False


async def test_nothing_found_says_so_and_accounts_are_separate(tools):
    assert (await tools.search(ME, "nothing", None))["message"] == "No matching notes."
    wrote = (await tools.write(ME, "Private", "mine only", [], ""))["file"]
    assert (await tools.search(OTHER, "private", None))["count"] == 0
    assert (await tools.read(OTHER, wrote["id"]))["ok"] is False
    assert (await tools.update(OTHER, wrote["id"], None, "x", None, None))["ok"] is False


async def test_the_quota_is_a_readable_refusal(tools):
    for name in "abc":
        assert (await tools.write(ME, name, "x", [], ""))["ok"]
    full = await tools.write(ME, "d", "x", [], "")
    assert full["ok"] is False and "limit" in full["message"]
