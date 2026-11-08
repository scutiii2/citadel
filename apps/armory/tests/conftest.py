from __future__ import annotations

import os

# Tests never read or create the shared token file.
os.environ["INTERNAL_TOKEN_FILE"] = ""

import dataclasses

import pytest

from src import errors
from src.config import settings as base_settings


@pytest.fixture(autouse=True)
def log_dir(tmp_path, monkeypatch):
    """Points errors.report()'s per-error files at a throwaway directory,
    so tests never write into the real logs/ directory."""
    test_settings = dataclasses.replace(base_settings, log_dir=tmp_path / "logs")
    monkeypatch.setattr(errors, "settings", test_settings)
    return test_settings.log_dir
