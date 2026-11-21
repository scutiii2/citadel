from datetime import datetime, timedelta, timezone

import pytest

from src.agents.gateway import Caller
from src.tickets.classifier import ClassifierUnavailable
from src.tickets.config import load_ticket_config
from src.tickets.service import TicketError, TicketNotFound, TicketService
from src.tickets.store import TicketStore

CALLER = Caller(username="ana", email="ana@example.com", uid="u-1")
NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class FakeClassifier:
    def __init__(self, tag=None, verdicts=None, down=False):
        self.tag, self.verdicts, self.down, self.tuned = tag, list(verdicts or []), down, None

    async def pick_tag(self, caller, ticket, tags):
        if self.down:
            raise ClassifierUnavailable("down")
        return self.tag

    async def same_issue(self, caller, new, existing):
        if self.down:
            raise ClassifierUnavailable("down")
        return self.verdicts.pop(0) if self.verdicts else "no"

    def tune(self, **kwargs):
        self.tuned = kwargs


def make(db_gateway, classifier=None, tmp_path=None, **config):
    store = TicketStore(db_gateway)
    path = None if tmp_path is None else tmp_path / "settings.db"
    return TicketService(store, load_ticket_config(config), classifier, clock=lambda: NOW, settings_path=path)


async def file(service, owner="u-1", **extra):
    base = dict(owner=owner, reporter="ana", type="bug", title="Email fails", description="It does not send",
                source="user", caller=CALLER)
    return await service.create(**{**base, **extra})


async def test_a_ticket_is_filed_with_its_own_group_and_the_requester_as_owner(db_gateway):
    service = make(db_gateway)
    outcome = await file(service)
    assert outcome.ticket["owner"] == "u-1" and outcome.ticket["reporter"] == "ana"
    assert outcome.duplicate is False and outcome.group_size == 1


@pytest.mark.parametrize("extra, message", [
    ({"type": "rant"}, "type must be one of"), ({"source": "robot"}, "source must be one of"),
    ({"title": "  "}, "title is required"), ({"description": "x" * 4001}, "limit is 4000"), ({"owner": " "}, "cannot be filed"),
])
async def test_bad_reports_are_refused_in_words(db_gateway, extra, message):
    with pytest.raises(TicketError, match=message):
        await file(make(db_gateway), **extra)


async def test_the_classifier_tags_and_groups_a_similar_report(db_gateway):
    classifier = FakeClassifier(tag="email", verdicts=["yes"])
    service = make(db_gateway, classifier)
    first = await file(service)
    second = await file(service, owner="u-2", title="Mail broken")
    assert first.ticket["tags"] == ["email"]
    assert second.ticket["group_id"] == first.ticket["group_id"] and second.group_size == 2


async def test_an_uncertain_verdict_marks_a_possible_group_without_joining(db_gateway):
    service = make(db_gateway, FakeClassifier(tag="email", verdicts=["uncertain"]))
    first = await file(service)
    second = await file(service, title="Maybe the same")
    assert second.ticket["group_id"] != first.ticket["group_id"]
    assert second.ticket["possible_group_id"] == first.ticket["group_id"]


async def test_a_classifier_that_is_down_leaves_the_ticket_ungrouped_and_untagged(db_gateway):
    service = make(db_gateway, FakeClassifier(down=True))
    outcome = await file(service)
    assert outcome.ticket["tags"] == [] and outcome.group_size == 1


async def test_no_caller_means_no_classification(db_gateway):
    classifier = FakeClassifier(tag="email")
    outcome = await file(make(db_gateway, classifier), caller=None)
    assert outcome.ticket["tags"] == []


async def test_a_manual_ticket_may_carry_custom_tags_but_an_automatic_one_may_not(db_gateway):
    service = make(db_gateway)
    manual = await file(service, tags=["my-tag", "email"])
    assert manual.ticket["tags"] == ["my-tag", "email"]
    auto = await file(service, source="ai_auto", tags=["my-tag", "email"], context={"tool_name": "t", "error_text": "boom"})
    assert auto.ticket["tags"] == ["email"]


async def test_an_identical_open_automatic_report_is_a_duplicate_and_the_cap_refuses_more(db_gateway):
    service = make(db_gateway, auto_hourly_cap=2)
    context = {"tool_name": "tool_x", "error_text": "Failed 12 times at /a/b"}
    first = await file(service, source="ai_auto", context=context)
    again = await file(service, source="ai_auto", context={**context, "error_text": "Failed 99 times at /c/d"})
    assert again.duplicate is True and again.ticket["id"] == first.ticket["id"]
    await file(service, source="ai_auto", context={"tool_name": "tool_y", "error_text": "other"})
    with pytest.raises(TicketError, match="Too many automatic reports"):
        await file(service, source="ai_auto", context={"tool_name": "tool_z", "error_text": "third"})


async def test_automatic_reports_are_redacted(db_gateway):
    outcome = await file(make(db_gateway), source="ai_auto", title="Key Bearer abcdefghijklmnopqrstuvwx failed",
                         context={"tool_name": "t", "error_text": "x"})
    assert "abcdefghijklmnopqrstuvwx" not in outcome.ticket["title"]


async def test_group_priority_rises_with_size_unless_pinned(db_gateway):
    service = make(db_gateway, FakeClassifier(verdicts=["yes", "yes", "yes"]),
                   elevation={"high": {"tickets": 3, "recent": 99}, "urgent": {"tickets": 99, "recent": 99}})
    for number in range(3):
        outcome = await file(service, owner=f"u-{number}", title=f"same {number}")
    assert outcome.ticket["effective_priority"] == "high"
    pinned = make(db_gateway, FakeClassifier(verdicts=["yes", "yes"]))
    first = await file(pinned, title="other group")
    await pinned.set_group_priority(first.ticket["group_id"], priority="low")
    assert (await pinned.get_ticket(first.ticket["id"]))["effective_priority"] == "normal"


async def test_someone_elses_ticket_looks_missing(db_gateway):
    service = make(db_gateway)
    ticket = (await file(service)).ticket
    assert (await service.get_ticket(ticket["id"], owner="u-1"))["comments"] == []
    for call in (service.get_ticket(ticket["id"], owner="u-2"),
                 service.add_comment(ticket["id"], author="bo", role="reporter", body="hi", owner="u-2"),
                 service.close_own(ticket["id"], "u-2"), service.reopen_own(ticket["id"], "u-2")):
        with pytest.raises(TicketNotFound):
            await call


async def test_comments_are_checked_and_ai_comments_redacted(db_gateway):
    service = make(db_gateway)
    ticket = (await file(service)).ticket
    with pytest.raises(TicketError, match="comment is required"):
        await service.add_comment(ticket["id"], author="ana", role="reporter", body=" ", owner="u-1")
    with pytest.raises(TicketError, match="role must be one of"):
        await service.add_comment(ticket["id"], author="ana", role="admin", body="x")
    saved = await service.add_comment(ticket["id"], author="ana", role="ai", body="key Bearer abcdefghijklmnopqrstuvwx", owner="u-1")
    assert "abcdefghijklmnopqrstuvwx" not in saved["comments"][0]["body"]


async def test_a_full_ticket_refuses_more_comments_in_words(db_gateway):
    from src.tickets import store as module

    service = make(db_gateway)
    ticket = (await file(service)).ticket
    for number in range(module.MAX_COMMENTS):
        await service.add_comment(ticket["id"], author="ana", role="reporter", body=f"c{number}", owner="u-1")
    with pytest.raises(TicketError, match="most comments"):
        await service.add_comment(ticket["id"], author="ana", role="reporter", body="more", owner="u-1")


async def test_reopening_only_works_on_a_finished_ticket(db_gateway):
    service = make(db_gateway)
    ticket = (await file(service)).ticket
    with pytest.raises(TicketError, match="Only resolved or closed"):
        await service.reopen_own(ticket["id"], "u-1")
    await service.close_own(ticket["id"], "u-1")
    assert (await service.reopen_own(ticket["id"], "u-1"))["status"] == "open"


async def test_staff_changes_validate_and_count_as_staff_activity(db_gateway):
    service = make(db_gateway)
    ticket = (await file(service)).ticket
    with pytest.raises(TicketError, match="status must be one of"):
        await service.update_ticket(ticket["id"], status="done")
    changed = await service.update_ticket(ticket["id"], status="in_progress", priority="high", assignee=" root ", tags=["Email"])
    assert (changed["status"], changed["priority"], changed["assignee"], changed["tags"]) == ("in_progress", "high", "root", ["email"])
    assert changed["last_staff_activity_at"] == NOW.isoformat()
    with pytest.raises(TicketNotFound):
        await service.move_ticket(ticket["id"], 99)


async def test_listing_everything_for_an_owner_needs_the_owner(db_gateway):
    service = make(db_gateway)
    await file(service)
    with pytest.raises(TicketError, match="owner is required"):
        await service.list_tickets(limit=None)
    assert len(await service.list_tickets(owner="u-1", limit=None)) == 1


async def test_settings_are_validated_saved_and_tune_the_classifier(db_gateway, tmp_path):
    classifier = FakeClassifier()
    service = make(db_gateway, classifier, tmp_path)
    document = service.settings_document()
    with pytest.raises(TicketError, match="Unknown setting"):
        await service.update_settings({"nope": 1})
    with pytest.raises(TicketError, match="2 to 10"):
        await service.update_settings({"tags": {"only": "one"}})
    saved = await service.update_settings({"auto_hourly_cap": 9, "laya": {"min_confidence": 0.8}})
    assert saved["auto_hourly_cap"] == 9 and saved["laya"]["candidates"] == document["laya"]["candidates"]
    assert classifier.tuned == {"min_confidence": 0.8, "timeout": document["laya"]["timeout_seconds"]}
    from src.tickets import settings as stored

    assert stored.load(tmp_path / "settings.db").auto_hourly_cap == 9


async def test_tag_options_list_the_vocabulary_then_the_owners_custom_tags(db_gateway):
    service = make(db_gateway)
    await file(service, tags=["my-tag"])
    values = [o["value"] for o in await service.tag_options("u-1")]
    assert values[-1] == "my-tag" and "email" in values
    assert "my-tag" not in [o["value"] for o in await service.tag_options("u-2")]
