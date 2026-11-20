import pytest

from src.brain.files import BrainFiles
from src.brain.global_brain import GLOBAL_UID, GlobalBrain
from src.brain.limits import LongTermLimits
from src.brain.skills import SkillFiles
from src.mcp_tools.brain_tools import BrainTools
from src.mcp_tools.scope import Account
from src.mcp_tools.skill_tools import SkillTools

ME = Account("u-1")


@pytest.fixture
def world(tmp_path):
    files = BrainFiles(tmp_path / "brain", LongTermLimits(), refresh_seconds=0.0)
    glob = GlobalBrain(tmp_path / "brain", LongTermLimits())
    glob.files._refresh = 0.0
    return type("World", (), {"files": files, "skills": SkillFiles(files), "glob": glob,
                              "brain": BrainTools(files, glob), "skill": SkillTools(SkillFiles(files), glob)})()


async def test_search_merges_own_and_global_and_labels_them(world):
    await world.files.create("u-1", title="Tea", body="I drink tea")
    await world.glob.files.create(GLOBAL_UID, title="House tea rules", body="tea is served at four")
    found = await world.brain.search(ME, "tea", None)
    assert found["count"] == 2
    by_scope = {r["scope"]: r for r in found["results"]}
    assert set(by_scope) == {"own", "global"} and by_scope["global"]["source_label"] == "global brain"
    assert by_scope["own"]["source_label"] == "written by the user"


async def test_an_own_file_wins_a_tie(world):
    await world.files.create("u-1", title="Tea", body="same words")
    await world.glob.files.create(GLOBAL_UID, title="Tea", body="same words")
    found = await world.brain.search(ME, "tea", 1)
    assert [r["scope"] for r in found["results"]] == ["own"]


async def test_read_falls_back_to_global_and_never_allows_edits(world):
    shared = await world.glob.files.create(GLOBAL_UID, title="Rules", body="be kind")
    read = await world.brain.read(ME, shared.id)
    assert read["ok"] and read["file"]["scope"] == "global" and read["file"]["agent_can_edit"] is False
    refused = await world.brain.update(ME, shared.id, None, "vandalised", None, None)
    assert refused["ok"] is False
    assert (await world.glob.files.get(GLOBAL_UID, shared.id)).body == "be kind"
    assert (await world.brain.read(ME, "0" * 32))["ok"] is False


async def test_list_can_browse_the_global_folder(world):
    await world.glob.files.create(GLOBAL_UID, title="Rules", body="x", folder="policy")
    own = await world.brain.list(ME, "", "own")
    assert own["folders"] == [] and own["files"] == []
    shared = await world.brain.list(ME, "policy", "global")
    assert shared["folders"] == ["policy"] and [f["title"] for f in shared["files"]] == ["Rules"]


async def test_skill_search_adds_global_skills_without_an_id(world):
    own, _ = await world.skills.propose("u-1", "Restart an app", "hung", "stop it, then start it", "")
    await world.skills.set_status("u-1", own.id, "active")
    shared, _ = await world.glob.skills.propose(GLOBAL_UID, "Restart a server", "server hung", "reboot the box", "")
    await world.glob.skills.set_status(GLOBAL_UID, shared.id, "active")
    found = await world.skill.search(ME, "restart")
    assert found["count"] == 2 and found["message"].startswith("2 approved skill(s):\n")
    assert f"[{own.id}] Restart an app" in found["message"] and "[global] Restart a server" in found["message"]
    assert own.id == shared.id == 1  # the same number in two stores
    marked = await world.skill.mark(ME, shared.id, "success")  # the number always means the account's own skill
    assert marked["recorded"] is True
    assert (await world.glob.skills.list(GLOBAL_UID))[0].successes == 0


async def test_a_global_skill_with_an_own_title_is_not_listed_twice(world):
    own, _ = await world.skills.propose("u-1", "Restart an app", "hung", "stop, start", "")
    await world.skills.set_status("u-1", own.id, "active")
    shared, _ = await world.glob.skills.propose(GLOBAL_UID, "restart AN app", "hung", "stop, start", "")
    await world.glob.skills.set_status(GLOBAL_UID, shared.id, "active")
    assert (await world.skill.search(ME, "restart"))["count"] == 1


async def test_no_tool_shares_imports_or_writes_global(client):
    names = {tool.name for tool in await client.app.state.mcp.list_tools()}
    assert not any("share" in name or "global" in name or "import" in name for name in names)


async def test_personal_results_survive_unavailable_global_storage(world, monkeypatch):
    async def unavailable(*_args):
        raise OSError("Unavailable storage")

    await world.files.create("u-1", title="Personal note", body="tea")
    own, _ = await world.skills.propose("u-1", "Make tea", "thirsty", "brew tea")
    await world.skills.set_status("u-1", own.id, "active")
    monkeypatch.setattr(world.glob.files, "search", unavailable)
    monkeypatch.setattr(world.glob.skills, "search", unavailable)

    notes = await world.brain.search(ME, "tea", None)
    assert [note["scope"] for note in notes["results"]] == ["own"]
    assert "Global brain search is unavailable." in notes["message"]
    skills = await world.skill.search(ME, "tea")
    assert skills["count"] == 1 and f"[{own.id}]" in skills["message"]
    assert "Global skill search is unavailable." in skills["message"]
