from src.brain.limits import StackLimits, load_limits
from src.citadel_auth import settings_store


def test_defaults_come_from_the_spec(tmp_path):
    assert load_limits(tmp_path / "settings.db") == StackLimits(40, 500, 1500, 0.8)


def test_saved_values_are_used_and_clamped(tmp_path):
    path = tmp_path / "settings.db"
    settings_store.put(path, "brain", "stack", {"max_items": 5, "max_item_chars": 99999, "warn_ratio": 7})
    limits = load_limits(path)
    assert limits.max_items == 5
    assert limits.max_item_chars == 2000   # ceiling
    assert limits.warn_ratio == 0.95       # ceiling


def test_junk_is_ignored(tmp_path):
    path = tmp_path / "settings.db"
    settings_store.put(path, "brain", "stack", {"max_items": "many", "warn_ratio": None})
    assert load_limits(path) == StackLimits()
