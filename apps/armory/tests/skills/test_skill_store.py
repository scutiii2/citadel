"""skill_store: owner scoping, the approval gate, caps and search."""

from __future__ import annotations

import pytest

from src.capabilities.skills.utils import skill_store as store


@pytest.fixture
def db(tmp_path):
    return tmp_path / "skills.db"


def propose(db, owner="alice", title="Restart an app", **kw):
    args = {"when_to_use": "an app is hung", "steps": "stop it, then start it", "tools": "tool_srv_stopApp"} | kw
    return store.propose(db, owner, title, **args)


def test_proposal_is_not_searchable_until_approved(db):
    skill_id = propose(db).id
    assert store.search(db, "alice", "restart") == []
    assert [s.status for s in store.list_skills(db, "alice")] == ["proposed"]

    assert store.set_status(db, "alice", skill_id, "active")
    found = store.search(db, "alice", "restarting hung apps")
    assert [s.id for s in found] == [skill_id]


def test_duplicate_title_is_stored_once_but_retired_one_can_be_proposed_again(db):
    first = propose(db)
    again = propose(db, title="  restart AN app ")
    assert again.duplicate and again.id == first.id

    store.set_status(db, "alice", first.id, "retired")
    assert not propose(db).duplicate


def test_owners_are_isolated(db):
    skill_id = propose(db).id
    store.set_status(db, "alice", skill_id, "active")
    assert store.search(db, "bob", "restart") == []
    assert not store.set_status(db, "bob", skill_id, "retired")
    assert not store.delete(db, "bob", skill_id)
    assert store.mark(db, "bob", skill_id, "success") is None
    assert len(store.search(db, "alice", "restart")) == 1


def test_no_owner_is_refused(db):
    with pytest.raises(store.SkillStoreError):
        store.propose(db, "  ", "t", "w", "s")
    with pytest.raises(store.SkillStoreError):
        store.search(db, "", "x")


def test_reading_never_creates_the_file(db):
    assert store.search(db, "alice", "x") == [] and store.list_skills(db, "alice") == []
    assert store.purge_owner(db, "alice") == 0
    assert not db.exists()


@pytest.mark.parametrize("field,limit", [("title", 80), ("when_to_use", 300), ("steps", 1200), ("tools", 200)])
def test_length_limits(db, field, limit):
    propose(db, **{field: "x" * limit} if field != "title" else {"title": "x" * limit})
    with pytest.raises(store.SkillStoreError, match="limit"):
        propose(db, **{field: "y" * (limit + 1)} if field != "title" else {"title": "y" * (limit + 1)})


def test_empty_required_fields_are_refused(db):
    with pytest.raises(store.SkillStoreError):
        propose(db, steps="   ")


def test_proposed_cap(db):
    for i in range(store.MAX_PROPOSED):
        propose(db, title=f"skill {i}")
    with pytest.raises(store.SkillStoreError, match="waiting for approval"):
        propose(db, title="one more")


def test_active_cap(db, monkeypatch):
    monkeypatch.setattr(store, "MAX_ACTIVE", 2)
    ids = [propose(db, title=f"skill {i}").id for i in range(3)]
    assert store.set_status(db, "alice", ids[0], "active") and store.set_status(db, "alice", ids[1], "active")
    with pytest.raises(store.SkillStoreError, match="active skills"):
        store.set_status(db, "alice", ids[2], "active")
    assert store.set_status(db, "alice", ids[0], "active")  # already active: not a new slot


def test_mark_counts_only_active_skills(db):
    skill_id = propose(db).id
    assert store.mark(db, "alice", skill_id, "success") is None
    store.set_status(db, "alice", skill_id, "active")
    store.mark(db, "alice", skill_id, "success")
    skill = store.mark(db, "alice", skill_id, "failure")
    assert (skill.successes, skill.failures) == (1, 1)
    with pytest.raises(store.SkillStoreError):
        store.mark(db, "alice", skill_id, "maybe")


def active(db, owner="alice", title="Restart an app"):
    skill_id = propose(db, owner=owner, title=title).id
    store.set_status(db, owner, skill_id, "active")
    return skill_id


def fail(db, skill_id, times):
    for _ in range(times):
        store.mark(db, "alice", skill_id, "failure")


def test_a_skill_that_keeps_failing_is_no_longer_offered(db):
    skill_id = active(db)
    store.mark(db, "alice", skill_id, "success")
    fail(db, skill_id, store.FAILING_MIN - 1)
    assert [s.id for s in store.search(db, "alice", "restart")] == [skill_id]  # two failures: still offered

    fail(db, skill_id, 1)  # 3 failures against 1 success
    skill = store.list_skills(db, "alice")[0]
    assert store.is_failing(skill)
    assert store.search(db, "alice", "restart") == [] and store.search(db, "alice") == []


def test_failures_that_do_not_outnumber_the_successes_do_not_quarantine(db):
    skill_id = active(db)
    for _ in range(3):
        store.mark(db, "alice", skill_id, "success")
    fail(db, skill_id, 3)  # 3 and 3: a tie is not "more often than it worked"
    assert not store.is_failing(store.list_skills(db, "alice")[0])
    assert len(store.search(db, "alice", "restart")) == 1


def test_editing_rewrites_the_skill_resets_the_counts_and_brings_it_back(db):
    skill_id = active(db)
    fail(db, skill_id, store.FAILING_MIN)
    assert store.search(db, "alice", "restart") == []

    edited = store.update(db, "alice", skill_id, "Reboot an app", "an app freezes", "kill it, then launch it", "tool_srv_restartApp")

    assert (edited.title, edited.status, edited.successes, edited.failures) == ("Reboot an app", "active", 0, 0)
    assert [s.id for s in store.search(db, "alice", "freezes")] == [skill_id]
    assert store.search(db, "alice", "hung") == []  # the index follows the new text


def test_editing_keeps_the_status_and_works_on_any_status(db):
    proposed = propose(db).id
    assert store.update(db, "alice", proposed, "New", "when", "steps").status == "proposed"
    assert store.search(db, "alice", "new") == []


def test_editing_is_owner_scoped_validated_and_refuses_a_duplicate_title(db):
    first = propose(db, title="First").id
    propose(db, title="Second")
    assert store.update(db, "bob", first, "T", "w", "s") is None
    assert store.update(db, "alice", 999, "T", "w", "s") is None
    with pytest.raises(store.SkillStoreError, match="already has that title"):
        store.update(db, "alice", first, " SECOND ", "w", "s")
    with pytest.raises(store.SkillStoreError):
        store.update(db, "alice", first, "T", "   ", "s")
    with pytest.raises(store.SkillStoreError, match="limit"):
        store.update(db, "alice", first, "T" * 81, "w", "s")
    assert store.update(db, "alice", first, "First", "w", "s").title == "First"  # its own title is fine


def test_editing_never_creates_the_file(db):
    assert store.update(db, "alice", 1, "T", "w", "s") is None and not db.exists()


def test_retired_skill_leaves_search(db):
    skill_id = propose(db).id
    store.set_status(db, "alice", skill_id, "active")
    store.set_status(db, "alice", skill_id, "retired")
    assert store.search(db, "alice", "restart") == []


def test_empty_query_lists_newest_active_up_to_limit(db):
    for i in range(5):
        store.set_status(db, "alice", propose(db, title=f"skill {i}").id, "active")
    assert [s.title for s in store.search(db, "alice")] == ["skill 4", "skill 3", "skill 2"]


def test_query_with_fts_syntax_is_treated_as_words(db):
    store.set_status(db, "alice", propose(db).id, "active")
    assert store.search(db, "alice", '") OR NOT * (') == []


def test_delete_and_purge_clear_the_index(db):
    first, second = propose(db, title="a one").id, propose(db, title="b two").id
    for skill_id in (first, second):
        store.set_status(db, "alice", skill_id, "active")
    assert store.delete(db, "alice", first)
    assert [s.id for s in store.search(db, "alice", "hung")] == [second]
    assert store.purge_owner(db, "alice") == 1
    assert store.search(db, "alice", "hung") == []
    assert store.set_status(db, "alice", 999, "active") is False
