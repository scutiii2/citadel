import asyncio
import os

import pytest

from src.brain.files import BrainError, BrainFiles
from src.brain.limits import LongTermLimits

U1, U2 = "u-1", "u-2"


@pytest.fixture
def files(tmp_path):
    return BrainFiles(tmp_path / "brain", LongTermLimits(max_record_chars=200, max_files=3, max_total_bytes=3000), refresh_seconds=0.0)


def home(files, uid=U1):
    return files._root / "accounts" / uid


async def refused(coro, status):
    with pytest.raises(BrainError) as error:
        await coro
    assert error.value.status == status
    return str(error.value)


async def test_create_read_list_and_delete(files):
    made = await files.create(U1, title="Tea notes", body="Likes **tea**.", tags=["Tea"], folder="drinks")
    assert (made.source, made.last_editor, made.revision, made.edited, made.tags) == ("manual", "user", 1, False, ("tea",))
    path = home(files) / "drinks" / f"tea-notes-{made.id[:8]}.md"
    assert path.is_file() and "Likes **tea**." in path.read_text(encoding="utf-8")
    assert await files.get(U1, made.id) == made
    assert [r.id for r in await files.list(U1)] == [made.id]
    assert [r.id for r in await files.list(U1, "drinks")] == [made.id] and await files.list(U1, "other") == []
    assert await files.folders(U1) == ["drinks"]
    await files.delete(U1, made.id)
    assert not path.exists() and not (home(files) / "drinks").exists()
    await refused(files.get(U1, made.id), 404)


async def test_nested_folders_list_their_parents(files):
    await files.create(U1, title="A", body="", folder="work/ideas/q1")
    assert await files.folders(U1) == ["work", "work/ideas", "work/ideas/q1"]


async def test_no_temporary_file_is_left_behind(files):
    await files.create(U1, title="A", body="x")
    assert [p.name for p in home(files).rglob("*") if p.is_file() and not p.name.endswith(".md")] == []


async def test_another_account_never_sees_a_file(files):
    made = await files.create(U1, title="Private", body="secret words")
    await refused(files.get(U2, made.id), 404)
    assert await files.list(U2) == [] and await files.search(U2, "secret") == []
    await refused(files.update(U2, made.id, body="x"), 404)
    await refused(files.delete(U2, made.id), 404)


@pytest.mark.parametrize("uid", ["../x", "a/b", "", "a" * 65, "u 1", "..", "x\\y"])
async def test_a_bad_account_id_is_refused(files, uid):
    await refused(files.list(uid), 400)


@pytest.mark.parametrize("folder", ["..", "a/../b", "/etc", "A", "a\\b", "a/b/c/d"])
async def test_an_unsafe_folder_is_refused_and_nothing_is_written(files, folder):
    await refused(files.create(U1, title="x", body="y", folder=folder), 422)
    assert not (files._root / "accounts").exists() or not list((files._root / "accounts").rglob("*.md"))


async def test_a_symlinked_folder_cannot_be_read_or_written_through(files, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "stolen.md").write_text("outside text", encoding="utf-8")
    home(files).mkdir(parents=True)
    try:
        os.symlink(outside, home(files) / "linked", target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
    assert await files.list(U1) == []
    await refused(files.create(U1, title="x", body="y", folder="linked"), 403)
    assert [p.name for p in outside.iterdir()] == ["stolen.md"]


async def test_a_symlinked_account_folder_is_not_followed(files, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (files._root / "accounts").mkdir(parents=True)
    try:
        os.symlink(outside, home(files), target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
    await refused(files.create(U1, title="x", body="y"), 403)
    assert list(outside.iterdir()) == []


async def test_field_limits(files):
    await refused(files.create(U1, title=" ", body="x"), 422)
    await refused(files.create(U1, title="t" * 201, body="x"), 422)
    await refused(files.create(U1, title="t", body="x" * 201), 422)
    await refused(files.create(U1, title="t", body="x", tags=["Bad Tag"]), 422)
    await refused(files.create(U1, title="t", body="x", tags=[f"t{i}" for i in range(11)]), 422)


async def test_the_file_count_and_the_byte_quota_are_enforced(files):
    for name in "abc":
        await files.create(U1, title=name, body="x")
    assert "3 files" in await refused(files.create(U1, title="d", body="x"), 409)
    assert (await files.summary(U1))["files"] == 3
    small = BrainFiles(files._root, LongTermLimits(max_record_chars=200, max_files=50, max_total_bytes=700), refresh_seconds=0.0)
    await small.create(U2, title="a", body="x" * 100)
    await refused(small.create(U2, title="b", body="x" * 200), 409)


async def test_quota_is_safe_under_concurrent_writes(files):
    results = await asyncio.gather(*(files.create(U1, title=f"n{i}", body="x") for i in range(6)), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 3
    assert (await files.summary(U1))["files"] == 3


async def test_update_bumps_the_revision_and_detects_a_stale_copy(files):
    made = await files.create(U1, title="Old", body="one")
    changed = await files.update(U1, made.id, title="New", body="two", expected_revision=1)
    assert (changed.title, changed.body, changed.revision, changed.last_editor) == ("New", "two", 2, "user")
    await refused(files.update(U1, made.id, body="three", expected_revision=1), 412)
    await refused(files.update(U1, made.id), 422)
    assert (await files.get(U1, made.id)).body == "two"


async def test_moving_a_file_between_folders(files):
    made = await files.create(U1, title="Move me", body="x", folder="a")
    moved = await files.update(U1, made.id, folder="b/c")
    assert moved.folder == "b/c" and (await files.get(U1, made.id)).folder == "b/c"
    assert not (home(files) / "a").exists() and any((home(files) / "b" / "c").glob("*.md"))


async def test_agents_write_automatic_files_and_edit_only_those(files):
    mine = await files.create(U1, title="Agent note", body="v1", actor="agent")
    assert (mine.source, mine.last_editor) == ("automatic", "agent")
    again = await files.update(U1, mine.id, actor="agent", body="v2")
    assert (again.body, again.edited, again.last_editor) == ("v2", False, "agent")
    user_file = await files.create(U1, title="User note", body="keep")
    assert "read-only" in await refused(files.update(U1, user_file.id, actor="agent", body="x"), 403)
    await refused(files.update(U1, mine.id, actor="agent", folder="x"), 403)
    await refused(files.update(U1, mine.id, actor="agent", agent_editable=True), 403)
    flagged = await files.update(U1, user_file.id, agent_editable=True)
    assert flagged.agent_editable is True and flagged.last_editor == "user"
    assert (await files.update(U1, user_file.id, actor="agent", body="agent was allowed")).body == "agent was allowed"
    assert (await files.get(U1, user_file.id)).edited is False


async def test_a_user_edit_of_an_automatic_file_keeps_the_original_and_can_be_reverted(files):
    made = await files.create(U1, title="Agent title", body="agent body", tags=["a"], actor="agent")
    first = await files.update(U1, made.id, body="user body")
    assert first.edited is True and first.source == "automatic" and first.last_editor == "user"
    original = home(files) / ".originals" / f"{made.id}.md"
    assert "agent body" in original.read_text(encoding="utf-8")
    await files.update(U1, made.id, body="user body 2")
    assert "agent body" in original.read_text(encoding="utf-8")
    back = await files.revert(U1, made.id)
    assert (back.body, back.title, back.edited, back.last_editor) == ("agent body", "Agent title", False, "agent")
    assert back.revision == 4 and not original.exists()
    await refused(files.revert(U1, made.id), 409)


async def test_a_manual_file_has_nothing_to_revert(files):
    made = await files.create(U1, title="Mine", body="x")
    await files.update(U1, made.id, body="y")
    assert not (home(files) / ".originals").exists()
    await refused(files.revert(U1, made.id), 409)


async def test_files_dropped_in_by_hand_are_adopted_and_broken_ones_skipped(files):
    (home(files) / "inbox").mkdir(parents=True)
    (home(files) / "inbox" / "todo.md").write_text("# Todo\nbuy milk\n", encoding="utf-8")
    (home(files) / "broken.md").write_text('---\nid: "nope"\n---\n\ntext\n', encoding="utf-8")
    (home(files) / "notes.txt").write_text("not markdown", encoding="utf-8")
    (home(files) / ".hidden.md").write_text("hidden", encoding="utf-8")
    listed = await files.list(U1)
    assert [(r.title, r.folder, r.source) for r in listed] == [("todo", "inbox", "manual")]
    assert (await files.summary(U1))["skipped"] == 1
    kept = listed[0].id
    saved = await files.update(U1, kept, body="# Todo\nbuy bread\n")
    assert saved.id == kept and (await files.get(U1, kept)).body == "# Todo\nbuy bread\n"
    assert (await files.list(U1))[0].id == kept


async def test_an_outside_change_is_seen_after_the_refresh_time(tmp_path):
    now = [0.0]
    store = BrainFiles(tmp_path / "brain", LongTermLimits(), refresh_seconds=30.0, monotonic=lambda: now[0])
    assert await store.list(U1) == []
    (tmp_path / "brain" / "accounts" / U1).mkdir(parents=True)
    (tmp_path / "brain" / "accounts" / U1 / "late.md").write_text("late", encoding="utf-8")
    assert await store.list(U1) == []
    now[0] = 31.0
    assert [r.title for r in await store.list(U1)] == ["late"]


async def test_search_ranks_the_accounts_own_files(files):
    await files.create(U1, title="Tea", body="about tea")
    await files.create(U1, title="Coffee", body="about coffee and a little tea")
    await files.create(U2, title="Tea elsewhere", body="tea")
    hits = await files.search(U1, "tea")
    assert [h.record.title for h in hits] == ["Tea", "Coffee"]
    assert hits[0].score > hits[1].score > 0 and "tea" in hits[0].snippet
    assert len(await files.search(U1, "tea", limit=1)) == 1
    assert await files.search(U1, "zzz") == []


async def test_purge_removes_the_account_folder_only(files):
    await files.create(U1, title="a", body="x")
    await files.create(U2, title="b", body="y")
    await files.purge(U1)
    assert not home(files).exists() and home(files, U2).exists()
    assert await files.list(U1) == [] and len(await files.list(U2)) == 1
    await files.purge(U1)


async def test_an_account_cannot_alias_another_account(files):
    other = await files.create(U2, title="private", body="x")
    try:
        os.symlink(home(files, U2), home(files), target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
    await refused(files.list(U1), 403)
    await refused(files.create(U1, title="x", body="y"), 403)
    await refused(files.purge(U1), 403)
    assert await files.get(U2, other.id) == other


async def test_revert_cannot_follow_a_link_to_another_account(files):
    file = await files.create(U1, title="automatic", body="initial", actor="agent")
    changed = await files.update(U1, file.id, body="edited")
    original = home(files) / ".originals" / f"{file.id}.md"
    await files.create(U2, title="private", body="x")
    outside = next(home(files, U2).glob("*.md"))
    original.unlink()
    try:
        os.symlink(outside, original)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
    await refused(files.revert(U1, file.id), 403)
    assert await files.get(U1, file.id) == changed


async def test_a_failed_move_preserves_the_original_location(files, monkeypatch):
    from src.brain import files as module

    record = await files.create(U1, title="move", body="x", folder="old")
    remove = module._remove

    def fail_to_remove_old(root, account, path):
        if path.parent.name == "old":
            raise PermissionError("blocked")
        remove(root, account, path)

    monkeypatch.setattr(module, "_remove", fail_to_remove_old)
    with pytest.raises(PermissionError):
        await files.update(U1, record.id, folder="new")
    assert await files.get(U1, record.id) == record
    assert not list((home(files) / "new").glob("*.md"))


async def test_revert_copy_counts_toward_the_byte_quota(files):
    from dataclasses import replace

    written = await files.create(U1, title="automatic", body="x" * 100, actor="agent")
    initial_size = (await files.summary(U1))["bytes"]
    files.limits = replace(files.limits, max_total_bytes=initial_size + 10)
    await refused(files.update(U1, written.id, body="y" * 100), 409)

    files.limits = replace(files.limits, max_total_bytes=initial_size * 3)
    await files.update(U1, written.id, body="y" * 100)
    assert (await files.summary(U1))["bytes"] == sum(path.stat().st_size for path in home(files).rglob("*.md"))
    await files.revert(U1, written.id)
    assert (await files.summary(U1))["bytes"] == next(home(files).glob("*.md")).stat().st_size


async def test_create_never_replaces_a_file_on_a_filename_collision(files, monkeypatch):
    from uuid import UUID

    from src.brain import files as module

    generated = iter([UUID(hex="a" * 32), UUID(hex="a" * 8 + "b" * 24)])
    monkeypatch.setattr(module.uuid, "uuid4", lambda: next(generated))
    first = await files.create(U1, title="same", body="original")
    await refused(files.create(U1, title="same", body="replacement"), 409)
    assert await files.get(U1, first.id) == first


async def test_deleted_accounts_cannot_be_recreated_by_an_in_flight_agent(files):
    await files.create(U1, title="first", body="x")
    await files.purge(U1)
    await refused(files.create(U1, title="late", body="x", actor="agent"), 404)
    assert not home(files).exists()


async def test_delete_can_retry_when_the_original_could_not_be_removed(files, monkeypatch):
    from src.brain import files as module

    record = await files.create(U1, title="automatic", body="initial", actor="agent")
    await files.update(U1, record.id, body="edited")
    original = home(files) / ".originals" / f"{record.id}.md"
    remove = module._remove

    def fail_to_remove_original(root, account, path):
        if path == original:
            raise PermissionError("blocked")
        remove(root, account, path)

    with monkeypatch.context() as blocked:
        blocked.setattr(module, "_remove", fail_to_remove_original)
        with pytest.raises(PermissionError):
            await files.delete(U1, record.id)
    await files.delete(U1, record.id)
    assert not original.exists()
