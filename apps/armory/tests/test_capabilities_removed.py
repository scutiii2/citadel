"""Plan 22: Armory no longer holds memory, notes or skills. Stronghold and the Brain own them."""

import importlib.util

import pytest


@pytest.mark.parametrize("name", ["memory", "notes", "skills"])
def test_removed_capability_cannot_be_imported(name):
    assert importlib.util.find_spec(f"src.capabilities.{name}") is None


@pytest.mark.parametrize("module", ["src.connection_routes", "src.services.dictation"])
def test_removed_module_cannot_be_imported(module):
    assert importlib.util.find_spec(module) is None


@pytest.mark.parametrize("name", ["obsidian", "vault"])
def test_obsidian_capabilities_cannot_be_imported(name):
    assert importlib.util.find_spec(f"src.capabilities.{name}") is None


def test_no_obsidian_or_vault_setting_is_left():
    from src.environment_settings import SPECS

    assert not [s for s in SPECS if s.field.startswith("obsidian_") or s.field == "vault_dir"]
