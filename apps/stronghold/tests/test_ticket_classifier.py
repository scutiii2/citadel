import asyncio

import pytest

from src.agents.gateway import Caller
from src.tickets.classifier import ClassifierUnavailable, TicketClassifier
from src.triage.questions import AskOutcome, TriageUnavailable

CALLER = Caller(username="ana", email="ana@example.com", uid="u-1")
NEW = {"title": "Email fails", "description": "It does not send"}
OLD = {"title": "Mail broken", "description": "Nothing is delivered"}


class FakeTriage:
    def __init__(self, answer=None, error=None, delay=0.0):
        self.answer, self.error, self.delay, self.calls = answer, error, delay, []

    async def ask(self, caller, kind, text, question, options, trace=False, levels=None):
        self.calls.append((caller, kind, text, question, options))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return AskOutcome(self.answer, {"agent_usage": [{"agent_id": "triage", "total_tokens": 10, "input_tokens": 6, "output_tokens": 4}]})


class FakeUsage:
    def __init__(self, blocked=False):
        self.blocked, self.records = blocked, []

    async def check(self, owner):
        return object() if self.blocked else None

    async def record(self, owner, turn_id, kind, chat_id, rows):
        self.records.append((owner, kind, chat_id, rows))
        return 10


def make(triage, usage=None, confidence=0.7, timeout=1.0):
    return TicketClassifier(triage, usage or FakeUsage(), min_confidence=confidence, timeout=timeout), triage


async def test_same_issue_reads_a_confident_yes_and_no():
    yes, triage = make(FakeTriage({"kind": "yes_no", "answer": "yes", "confidence": 0.9, "uncertain": False}))
    assert await yes.same_issue(CALLER, NEW, OLD) == "yes"
    caller, kind, text, question, options = triage.calls[0]
    assert caller == CALLER and kind == "yes_no" and "Email fails" in text and "Mail broken" in text and options == []
    no, _ = make(FakeTriage({"kind": "yes_no", "answer": "no", "confidence": 0.9, "uncertain": False}))
    assert await no.same_issue(CALLER, NEW, OLD) == "no"


async def test_an_uncertain_or_weak_answer_is_uncertain():
    flagged, _ = make(FakeTriage({"kind": "yes_no", "answer": "yes", "confidence": 0.9, "uncertain": True}))
    assert await flagged.same_issue(CALLER, NEW, OLD) == "uncertain"
    weak, _ = make(FakeTriage({"kind": "yes_no", "answer": "yes", "confidence": 0.5, "uncertain": False}), confidence=0.7)
    assert await weak.same_issue(CALLER, NEW, OLD) == "uncertain"


async def test_pick_tag_returns_a_known_confident_tag_only():
    tags = {"email": "Mail problems", "ui": "Looks wrong"}
    good, triage = make(FakeTriage({"kind": "choice", "choice": "email", "confidence": 0.9, "uncertain": False}))
    assert await good.pick_tag(CALLER, NEW, tags) == "email"
    options = triage.calls[0][4]
    assert [(o.title, o.description) for o in options] == [("email", "Mail problems"), ("ui", "Looks wrong")]
    unknown, _ = make(FakeTriage({"kind": "choice", "choice": "weather", "confidence": 0.9, "uncertain": False}))
    assert await unknown.pick_tag(CALLER, NEW, tags) is None
    unsure, _ = make(FakeTriage({"kind": "choice", "choice": "email", "confidence": 0.9, "uncertain": True}))
    assert await unsure.pick_tag(CALLER, NEW, tags) is None


async def test_the_tokens_count_for_the_reporter():
    usage = FakeUsage()
    classifier, _ = make(FakeTriage({"kind": "yes_no", "answer": "no", "confidence": 0.9, "uncertain": False}), usage)
    await classifier.same_issue(CALLER, NEW, OLD)
    owner, kind, chat_id, rows = usage.records[0]
    assert (owner, kind, chat_id) == ("u-1", "ticket", None) and rows[0]["total_tokens"] == 10


async def test_it_gives_up_without_guessing():
    for triage in (FakeTriage(error=TriageUnavailable("down")), FakeTriage(delay=0.5)):
        classifier, _ = make(triage, timeout=0.05)
        with pytest.raises(ClassifierUnavailable):
            await classifier.same_issue(CALLER, NEW, OLD)
    blocked, triage = make(FakeTriage({"kind": "yes_no", "answer": "yes", "confidence": 1, "uncertain": False}), FakeUsage(blocked=True))
    with pytest.raises(ClassifierUnavailable):
        await blocked.pick_tag(CALLER, NEW, {"a": "b", "c": "d"})
    assert triage.calls == []


async def test_new_limits_apply_to_the_next_question():
    classifier, _ = make(FakeTriage({"kind": "yes_no", "answer": "yes", "confidence": 0.8, "uncertain": False}), confidence=0.9)
    assert await classifier.same_issue(CALLER, NEW, OLD) == "uncertain"
    classifier.tune(min_confidence=0.5, timeout=1.0)
    assert await classifier.same_issue(CALLER, NEW, OLD) == "yes"
