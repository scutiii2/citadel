from __future__ import annotations

import pytest

from src.capabilities.tickets.utils import rules

ELEVATION = {"high": {"tickets": 3, "recent": 2}, "urgent": {"tickets": 6, "recent": 4}}


def test_higher_priority_picks_the_more_urgent():
    assert rules.higher_priority("low", "high") == "high"
    assert rules.higher_priority("urgent", "normal") == "urgent"
    assert rules.higher_priority("normal", "normal") == "normal"


def test_fingerprint_ignores_numbers_paths_and_ids():
    a = rules.fingerprint("tool_email_sendEmail", "Missing key 'smtp_host' in C:\\cfg\\a.json line 12")
    b = rules.fingerprint("tool_email_sendEmail", "Missing key 'smtp_host' in D:\\x\\b.json line 99")
    c = rules.fingerprint("tool_email_sendEmail", "missing   key 'smtp_host' in /etc/app/c.json line 3")
    assert a == b == c
    assert len(a) == 16


def test_fingerprint_differs_by_tool_and_message():
    base = rules.fingerprint("tool_a", "boom")
    assert rules.fingerprint("tool_b", "boom") != base
    assert rules.fingerprint("tool_a", "different") != base
    assert rules.fingerprint(None, None) == rules.fingerprint("", "")


def test_clean_tags_keeps_known_unique_and_capped():
    vocabulary = ["config", "auth", "ui", "chat", "email", "performance", "other"]
    assert rules.clean_tags([" Config ", "auth", "AUTH", "nope"], vocabulary) == ["config", "auth"]
    assert rules.clean_tags(None, vocabulary) == []
    assert len(rules.clean_tags(vocabulary, vocabulary)) == 5


@pytest.mark.parametrize("priority, tickets, recent, expected", [
    ("normal", 2, 0, "normal"), ("normal", 3, 0, "high"), ("normal", 6, 0, "urgent"),  # by ticket count
    ("normal", 2, 1, "normal"), ("normal", 2, 2, "high"), ("normal", 2, 4, "urgent"),  # by recent rate
    ("urgent", 1, 0, "urgent"), ("high", 1, 0, "high"), ("high", 3, 0, "high"),  # never lowers
])
def test_elevation(priority, tickets, recent, expected):
    assert rules.elevated_priority(priority, tickets, recent, ELEVATION) == expected


def test_elevation_with_no_rules_changes_nothing():
    assert rules.elevated_priority("low", 100, 100, {}) == "low"


def test_custom_tags_are_normalized_unique_and_capped():
    tags = [" Mobile Bug ", "mobile-bug", "ui", "", "new-one", "new-two", "new-three", "new-four"]
    assert rules.clean_tags(tags, ["ui"], allow_custom=True) == ["mobile-bug", "ui", "new-one", "new-two", "new-three"]
