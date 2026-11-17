from __future__ import annotations

import pytest

from src.capabilities.tickets.utils.config import DEFAULT_TAGS, load_ticket_config


def test_no_settings_give_defaults():
    config = load_ticket_config()

    assert config.tags == DEFAULT_TAGS
    assert 2 <= len(config.tags) <= 10
    assert config.auto_hourly_cap == 5
    assert config.recent_hours == 24
    assert config.elevation == {"high": {"tickets": 3, "recent": 2}, "urgent": {"tickets": 6, "recent": 4}}
    assert config.laya_min_confidence == 0.7
    assert config.laya_candidates == 5
    assert config.laya_timeout_seconds == 20.0


def test_settings_override_only_what_they_name():
    config = load_ticket_config({"auto_hourly_cap": 2, "laya": {"candidates": 3}})

    assert config.auto_hourly_cap == 2
    assert config.laya_candidates == 3
    assert config.laya_timeout_seconds == 20.0
    assert config.tags == DEFAULT_TAGS


@pytest.mark.parametrize(
    "raw",
    [
        {"tags": {"only-one": "x"}},
        {"tags": {f"t{i}": "d" for i in range(11)}},
        {"tags": {"a": "", "b": "d"}},
        {"auto_hourly_cap": 0},
        {"elevation": {"critical": {"tickets": 1, "recent": 1}}},
        {"elevation": {"high": {"tickets": 0, "recent": 1}}},
        {"laya": {"min_confidence": 1.5}},
        {"laya": {"timeout_seconds": 0}},
    ],
)
def test_bad_values_are_rejected(raw):
    with pytest.raises(ValueError):
        load_ticket_config(raw)


def test_a_non_object_is_rejected():
    with pytest.raises(ValueError, match="must be an object"):
        load_ticket_config(["tags"])


def test_the_document_round_trips():
    config = load_ticket_config({"auto_hourly_cap": 2})

    assert load_ticket_config(config.document()) == config
