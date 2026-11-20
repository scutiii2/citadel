import dataclasses
from types import SimpleNamespace

import pytest

from src.brain import admin_settings
from src.brain.limits import SHARING_RANGES, LongTermLimits, SharingLimits, StackLimits, load_sharing
from src.citadel_auth import settings_store


def test_defaults_and_ranges():
    assert dataclasses.asdict(SharingLimits()) == {
        "max_share_chars": 20_000, "max_pending_sent": 30, "max_inbox": 100, "max_global_queue": 200}
    assert set(SHARING_RANGES) == set(dataclasses.asdict(SharingLimits()))


def test_saved_values_are_clamped_and_bad_ones_fall_back(tmp_path):
    path = tmp_path / "settings.db"
    assert load_sharing(path) == SharingLimits()
    settings_store.put(path, "brain", "sharing", {"max_share_chars": 10, "max_inbox": 5, "max_pending_sent": "x", "max_global_queue": True})
    loaded = load_sharing(path)
    assert (loaded.max_share_chars, loaded.max_inbox, loaded.max_pending_sent, loaded.max_global_queue) == (200, 5, 30, 200)


def test_the_admin_update_saves_and_applies_sharing_and_global_long_term(tmp_path):
    path = tmp_path / "settings.db"
    shares = SimpleNamespace(limits=SharingLimits())
    files = SimpleNamespace(limits=LongTermLimits())
    other = SimpleNamespace(limits=files.limits)
    stacks = SimpleNamespace(limits=StackLimits())
    admin_settings.update(stacks, files, path, {"sharing": {"max_inbox": 7}, "long_term": {"max_files": 9}},
                          shares=shares, global_files=other)
    assert shares.limits.max_inbox == 7 and files.limits.max_files == 9 and other.limits.max_files == 9
    assert load_sharing(path).max_inbox == 7
    shown = admin_settings.view(stacks, files, tmp_path, path, shares=shares)
    assert shown["sharing"]["max_inbox"] == 7 and shown["ranges"]["sharing"]["max_inbox"] == [1, 1000]
    assert shown["stored"]["sharing"] is True


@pytest.mark.parametrize("bad", [{"sharing": {"max_inbox": 0}}, {"sharing": {"nope": 1}}, {"sharing": {"max_inbox": 1.5}}, {"sharing": {}}])
def test_a_bad_sharing_change_saves_nothing(tmp_path, bad):
    path = tmp_path / "settings.db"
    shares = SimpleNamespace(limits=SharingLimits())
    files = SimpleNamespace(limits=SimpleNamespace())
    with pytest.raises(admin_settings.BrainSettingsError):
        admin_settings.update(SimpleNamespace(), files, path, bad, shares=shares)
    assert load_sharing(path) == SharingLimits() and shares.limits == SharingLimits()
