import asyncio

import pytest

from src.tickets.store import AutoLimit, CommentLimit, TicketStore

T0 = "2026-01-01T00:00:00+00:00"
T1 = "2026-01-01T01:00:00+00:00"
T2 = "2026-01-01T02:00:00+00:00"


def draft(owner="u-1", **extra):
    base = dict(owner=owner, reporter="ana", type="bug", title="Email fails", description="It does not send",
                source="user", tags=["email"], context={}, fingerprint=None, group_id=None,
                possible_group_id=None, now=T0)
    return {**base, **extra}


@pytest.fixture
def store(db_gateway):
    return TicketStore(db_gateway)


async def test_ids_count_up_and_a_new_ticket_makes_its_own_group(store):
    first = await store.insert_ticket(**draft())
    second = await store.insert_ticket(**draft(title="Other"))
    assert first == (1, True, 1) and second == (2, True, 2)
    ticket = await store.get_ticket(1)
    assert ticket["title"] == "Email fails" and ticket["effective_priority"] == "normal"
    assert "fingerprint" not in ticket and "comments" not in ticket


async def test_two_requests_at_once_get_different_ids(store):
    results = await asyncio.gather(*(store.insert_ticket(**draft(title=f"t{n}")) for n in range(8)))
    assert sorted(r[0] for r in results) == list(range(1, 9))


async def test_a_ticket_joins_an_existing_group(store):
    await store.insert_ticket(**draft())
    ticket_id, created, group_id = await store.insert_ticket(**draft(owner="u-2", group_id=1, now=T1))
    assert (ticket_id, created, group_id) == (2, True, 1)
    assert await store.group_counts(1, T0) == (2, 2)
    assert await store.group_counts(1, T1) == (2, 1)


async def test_an_open_automatic_report_is_not_filed_twice_but_a_closed_one_is(store):
    auto = draft(source="ai_auto", fingerprint="abc", auto_cap=5, auto_since=T0)
    first = await store.insert_ticket(**auto)
    again = await store.insert_ticket(**auto)
    assert again == (first[0], False, first[2])
    await store.update_ticket(first[0], {"status": "closed"}, T1)
    third = await store.insert_ticket(**auto)
    assert third[1] is True and third[0] != first[0]


async def test_the_automatic_cap_counts_one_owner_in_the_window(store):
    for n in range(2):
        await store.insert_ticket(**draft(source="ai_auto", fingerprint=f"f{n}", auto_cap=2, auto_since=T0))
    with pytest.raises(AutoLimit):
        await store.insert_ticket(**draft(source="ai_auto", fingerprint="f9", auto_cap=2, auto_since=T0))
    other = await store.insert_ticket(**draft(owner="u-2", source="ai_auto", fingerprint="f9", auto_cap=2, auto_since=T0))
    assert other[1] is True


async def test_lists_filter_and_come_newest_first(store):
    await store.insert_ticket(**draft(title="a", tags=["email"]))
    await store.insert_ticket(**draft(title="b", tags=["ui"], type="feature"))
    await store.insert_ticket(**draft(owner="u-2", title="c", tags=["email"]))
    assert [t["title"] for t in await store.list_tickets()] == ["c", "b", "a"]
    assert [t["title"] for t in await store.list_tickets(owner="u-1")] == ["b", "a"]
    assert [t["title"] for t in await store.list_tickets(tag="email")] == ["c", "a"]
    assert [t["title"] for t in await store.list_tickets(type="feature")] == ["b"]
    assert [t["title"] for t in await store.list_tickets(limit=1)] == ["c"]
    await store.update_ticket(1, {"status": "resolved"}, T1)
    assert [t["title"] for t in await store.list_tickets(status="resolved")] == ["a"]


async def test_the_group_priority_raises_the_effective_priority_and_a_filter_uses_it(store):
    await store.insert_ticket(**draft())
    assert await store.elevate_group(1, "high", T1) is True
    assert (await store.get_ticket(1))["effective_priority"] == "high"
    assert [t["id"] for t in await store.list_tickets(priority="high")] == [1]
    assert await store.list_tickets(priority="normal") == []
    assert await store.elevate_group(1, "normal", T2) is False  # never lowers
    await store.update_group(1, priority="low", pinned=True, now=T2)
    assert await store.elevate_group(1, "urgent", T2) is False  # pinned
    assert (await store.get_group(1))["priority_pinned"] is True


async def test_comments_keep_order_and_only_staff_comments_set_staff_activity(store):
    await store.insert_ticket(**draft())
    assert await store.add_comment(1, "ana", "reporter", "more info", T1) == 1
    assert (await store.get_ticket(1))["last_staff_activity_at"] is None
    assert await store.add_comment(1, "root", "staff", "looking", T2) == 2
    assert (await store.get_ticket(1))["last_staff_activity_at"] == T2
    assert [c["body"] for c in await store.list_comments(1)] == ["more info", "looking"]
    assert (await store.list_comments(1))[0]["ticket_id"] == 1
    assert await store.add_comment(99, "ana", "reporter", "x", T2) is None


async def test_a_ticket_holds_a_limited_number_of_comments(store):
    from src.tickets import store as module

    await store.insert_ticket(**draft())
    for n in range(module.MAX_COMMENTS):
        await store.add_comment(1, "ana", "reporter", f"c{n}", T1)
    with pytest.raises(CommentLimit):
        await store.add_comment(1, "ana", "reporter", "one too many", T1)


async def test_reopening_is_scoped_to_the_owner_and_records_a_system_comment(store):
    await store.insert_ticket(**draft())
    assert await store.reopen_own(1, "u-2", T1) is None
    assert await store.reopen_own(1, "u-1", T1) is False
    await store.update_ticket(1, {"status": "closed"}, T1)
    assert (await store.get_ticket(1))["closed_at"] == T1
    assert await store.reopen_own(1, "u-1", T2) is True
    ticket = await store.get_ticket(1)
    assert ticket["status"] == "open" and ticket["closed_at"] is None
    assert (await store.list_comments(1))[-1]["author_role"] == "system"


async def test_moving_a_ticket_to_a_group_a_new_group_or_a_missing_group(store):
    await store.insert_ticket(**draft())
    await store.insert_ticket(**draft(title="b"))
    assert await store.move_ticket(2, 1, T1) == 1
    assert (await store.get_ticket(2))["last_staff_activity_at"] == T1
    assert await store.move_ticket(2, None, T2) == 3
    assert await store.move_ticket(2, 77, T2) is None
    assert await store.move_ticket(99, 1, T2) is None


async def test_candidates_are_the_newest_open_ticket_of_each_group_with_a_shared_tag(store):
    await store.insert_ticket(**draft(title="a", tags=["email"]))
    await store.insert_ticket(**draft(title="b", tags=["email"], group_id=1))
    await store.insert_ticket(**draft(title="c", tags=["ui"]))
    await store.insert_ticket(**draft(title="d", tags=["email"], type="feature"))
    found = await store.candidates("bug", ["email"], 5)
    assert [t["title"] for t in found] == ["b"]
    assert [t["title"] for t in await store.candidates("bug", [], 5)] == ["c", "b"]
    await store.update_ticket(3, {"status": "closed"}, T1)
    assert [t["title"] for t in await store.candidates("bug", [], 5)] == ["b"]


async def test_groups_stats_and_owner_tags(store):
    await store.insert_ticket(**draft(tags=["email"]))
    await store.insert_ticket(**draft(title="b", tags=["ui"], group_id=1, now=T1))
    await store.insert_ticket(**draft(owner="u-2", title="c", tags=["custom"]))
    await store.update_ticket(3, {"priority": "urgent"}, T2)
    groups = await store.list_groups(since=T1)
    assert [g["id"] for g in groups] == [2, 1]  # most recent activity first
    first = next(g for g in groups if g["id"] == 1)
    assert (first["ticket_count"], first["recent_count"], first["open_count"]) == (2, 1, 2)
    assert first["tags"] == ["email", "ui"]
    assert [g["id"] for g in await store.list_groups(since=T1, tag="custom")] == [2]
    assert await store.stats() == {"open": 3, "urgent": 1, "groups": 2}
    assert await store.owner_tags("u-1") == ["email", "ui"]


async def test_purging_an_owner_deletes_only_their_tickets(store):
    await store.insert_ticket(**draft())
    await store.insert_ticket(**draft(owner="u-2", title="b"))
    assert await store.purge_owner("u-1") == 1
    assert await store.get_ticket(1) is None and await store.get_ticket(2) is not None
