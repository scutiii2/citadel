from __future__ import annotations

import os


import dataclasses

import pytest

from src import errors
from src.config import settings as base_settings


@pytest.fixture(scope="session")
def auth_stack(tmp_path_factory):
    import asyncio
    from src.citadel_auth.testing import make_stack
    from tests import auth_helpers
    auth_helpers.stack = asyncio.run(make_stack(tmp_path_factory.mktemp("service-auth")))
    return auth_helpers.stack


@pytest.fixture(autouse=True)
def service_identity(auth_stack, monkeypatch):
    import sys
    from src.services import service_auth
    monkeypatch.setattr(service_auth, "keyring", auth_stack["armory"])
    for name in ("src.services.extensions", "src.capabilities.obsidian.utils.brain_resolver"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "keyring"):
            monkeypatch.setattr(module, "keyring", auth_stack["armory"])


@pytest.fixture(autouse=True)
def log_dir(tmp_path, monkeypatch):
    """Points errors.report()'s per-error files at a throwaway directory,
    so tests never write into the real logs/ directory."""
    test_settings = dataclasses.replace(base_settings, log_dir=tmp_path / "logs")
    monkeypatch.setattr(errors, "settings", test_settings)
    return test_settings.log_dir
