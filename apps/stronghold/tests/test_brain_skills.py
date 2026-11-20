import os

import pytest

from src.brain import skills as skill_module
from src.brain.files import BrainError, BrainFiles
from src.brain.limits import LongTermLimits
from src.brain.skills import SkillFiles

U1, U2 = "u-1", "u-2"


@pytest.fixture
def brain(tmp_path):
    return BrainFiles(tmp_path / "brain", LongTermLimits(), refresh_seconds=0.0)


@pytest.fixture
def skills(brain):
    return SkillFiles(brain)


def folder(brain, uid=U1):
    return brain.root / "accounts" / uid / ".skills"


async def propose(skills, uid=U1, title="Restart an app", **extra):
    fields = {"when_to_use": "an app is hung", "steps": "stop it, then start it", "tools": "tool_srv_stopApp", **extra}
    skill, _ = await skills.propose(uid, title, **fields)
    return skill


async def refused(coro, status):
    with pytest.raises(BrainError) as error:
        await coro
    assert error.value.status == status
    return str(error.value)


async def test_a_proposal_is_hidden_until_the_user_approves_it(skills):
    made = await propose(skills)
    assert (made.id, made.status, made.successes, made.failures, made.failing) == (1, "proposed", 0, 0, False)
    assert await skills.search(U1, "app hung") == []
    assert (await skills.set_status(U1, made.id, "active")).status == "active"
    assert [s.id for s in await skills.search(U1, "app hung")] == [1]
    assert [s.id for s in await skills.search(U1, "")] == [1]  # no words: the newest active skills
    assert (await skills.set_status(U1, made.id, "retired")).status == "retired"
    assert await skills.search(U1, "app hung") == []


async def test_search_ranks_by_words_and_honours_the_limit(skills):
    first = await propose(skills, title="Restart an app")
    second = await propose(skills, title="Rotate logs", when_to_use="logs are large", steps="rotate, then compress", tools="")
    for skill in (first, second):
        await skills.set_status(U1, skill.id, "active")
    assert [s.id for s in await skills.search(U1, "rotate logs")] == [second.id]
    assert [s.id for s in await skills.search(U1, "")] == [second.id, first.id]  # newest first
    assert len(await skills.search(U1, "", limit=1)) == 1
    assert await skills.search(U1, "kubernetes") == []


async def test_the_same_title_is_stored_once_unless_the_first_was_retired(skills):
    first = await propose(skills)
    again, duplicate = await skills.propose(U1, "  restart   AN app ", "other", "other", "")
    assert duplicate is True and again.id == first.id
    await skills.set_status(U1, first.id, "retired")
    fresh, duplicate = await skills.propose(U1, "Restart an app", "an app is hung", "stop it", "")
    assert duplicate is False and fresh.id == 2


async def test_limits_on_text_and_on_counts(skills, monkeypatch):
    assert "title" in await refused(skills.propose(U1, "x" * 81, "w", "s", ""), 422)
    assert "when_to_use" in await refused(skills.propose(U1, "t", "w" * 301, "s", ""), 422)
    assert "steps" in await refused(skills.propose(U1, "t", "w", "s" * 1201, ""), 422)
    assert "tools" in await refused(skills.propose(U1, "t", "w", "s", "x" * 201), 422)
    await refused(skills.propose(U1, " ", "w", "s", ""), 422)
    monkeypatch.setattr(skill_module, "MAX_PROPOSED", 2)
    monkeypatch.setattr(skill_module, "MAX_ACTIVE", 1)
    one, two = await propose(skills, title="One"), await propose(skills, title="Two")
    assert "waiting for approval" in await refused(skills.propose(U1, "Three", "w", "s", ""), 409)
    await skills.set_status(U1, one.id, "active")
    assert "active skills" in await refused(skills.set_status(U1, two.id, "active"), 409)
    assert (await skills.set_status(U1, one.id, "active")).status == "active"  # already active: no new slot
    monkeypatch.setattr(skill_module, "MAX_SKILLS", 2)
    monkeypatch.setattr(skill_module, "MAX_PROPOSED", 20)
    assert "full" in await refused(skills.propose(U1, "Four", "w", "s", ""), 409)
    await refused(skills.set_status(U1, one.id, "banana"), 422)


async def test_marks_count_and_a_failing_skill_is_no_longer_offered(skills):
    made = await propose(skills)
    assert await skills.mark(U1, made.id, "success") is None  # not active yet
    await skills.set_status(U1, made.id, "active")
    assert (await skills.mark(U1, made.id, "success")).successes == 1
    for _ in range(3):
        last = await skills.mark(U1, made.id, "failure")
    assert (last.successes, last.failures, last.failing) == (1, 3, True)
    assert await skills.search(U1, "app hung") == []
    assert (await skills.list(U1))[0].failing is True
    edited = await skills.update(U1, made.id, "Restart an app", "an app is hung", "kill it, then launch it", "")
    assert (edited.successes, edited.failures, edited.failing, edited.status) == (0, 0, False, "active")
    assert [s.id for s in await skills.search(U1, "app hung")] == [made.id]
    await refused(skills.mark(U1, made.id, "banana"), 422)
    assert await skills.mark(U1, 99, "success") is None


async def test_update_refuses_another_skills_title_and_a_missing_skill(skills):
    one, two = await propose(skills, title="One"), await propose(skills, title="Two")
    assert "another skill" in (await refused(skills.update(U1, two.id, "one", "w", "s", ""), 409)).lower()
    assert await skills.update(U1, 99, "New", "w", "s", "") is None
    same = await skills.update(U1, one.id, "One", "w2", "s2", "")
    assert same.when_to_use == "w2"


async def test_delete_and_accounts_are_separate(skills):
    made = await propose(skills)
    assert await skills.list(U2) == []
    assert await skills.delete(U2, made.id) is False
    assert await skills.set_status(U2, made.id, "active") is None
    assert await skills.mark(U2, made.id, "success") is None
    assert await skills.delete(U1, made.id) is True
    assert await skills.delete(U1, made.id) is False
    assert await skills.list(U1) == []


async def test_a_skill_is_a_markdown_file_that_survives_awkward_text(skills, brain):
    made = await propose(skills, title='He said "hi"', steps="line one   line two")
    text = (folder(brain) / f"{made.id}.md").read_text(encoding="utf-8")
    assert text.startswith('---\nid: 1\ntitle: "He said \\"hi\\""\n') and text.endswith("\n---\n\nline one line two\n")
    assert (await skills.list(U1))[0].title == 'He said "hi"'


async def test_damaged_or_foreign_files_are_skipped_and_ids_keep_counting(skills, brain):
    made = await propose(skills)
    (folder(brain) / "9.md").write_text("no header at all", encoding="utf-8")
    (folder(brain) / "notes.md").write_text("---\nid: 1\n---\n", encoding="utf-8")
    (folder(brain) / "2.md").write_text((folder(brain) / "1.md").read_text(encoding="utf-8"), encoding="utf-8")  # id 1 inside 2.md
    assert [s.id for s in await skills.list(U1)] == [made.id]
    assert (await propose(skills, title="Next")).id == 2


async def test_purge_removes_only_skills_and_a_purged_account_is_refused(skills, brain):
    await brain.create(U1, title="A note", body="keep me")
    await propose(skills)
    await skills.purge(U1)
    assert not folder(brain).exists() and await skills.list(U1) == []
    assert (await brain.list(U1))[0].title == "A note"
    await skills.purge(U1)  # nothing left: still fine
    await propose(skills)
    await brain.purge(U1)
    await refused(skills.propose(U1, "Again", "w", "s", ""), 404)
    await skills.purge(U1)  # an account the brain already purged: quiet


@pytest.mark.parametrize("inside_account", [False, True])
async def test_a_skills_folder_that_is_a_link_is_never_followed(skills, brain, tmp_path, inside_account):
    await brain.create(U1, title="A note", body="x")
    outside = folder(brain).parent / "ordinary" if inside_account else tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, folder(brain), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    assert await skills.list(U1) == []
    await refused(skills.propose(U1, "Escape", "w", "s", ""), 403)
    assert list(outside.iterdir()) == []


async def test_a_bad_account_is_refused(skills):
    await refused(skills.list("../x"), 400)
