"""Plan 22: Armory no longer holds memory, notes or skills. Stronghold and the Brain own them."""

import importlib.util

import pytest


@pytest.mark.parametrize("name", ["memory", "notes", "skills"])
def test_removed_capability_cannot_be_imported(name):
    assert importlib.util.find_spec(f"src.capabilities.{name}") is None
