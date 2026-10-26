"""Tests for services/capability_base.py: identity registration, folder inference and the routes hook."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette

from src.services import capability_meta
from src.services.capability_base import Capability


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})


class Widgets(Capability):
    id = "wid"
    label = "Widgets"
    process_lifetime_modules = ("utils",)


def test_registers_identity_under_the_defining_module_folder():
    Widgets.__module__ = "pkg.capabilities.widgets"
    capability = Widgets()

    assert capability.folder == "widgets"
    assert capability_meta.for_folder("widgets") == capability.meta
    assert capability.meta.id == "wid" and capability.meta.label == "Widgets"


def test_a_second_instance_for_the_same_folder_is_refused():
    Widgets.__module__ = "pkg.capabilities.widgets"
    Widgets()

    with pytest.raises(ValueError):
        Widgets()


def test_process_lifetime_modules_default_to_none():
    class Plain(Capability):
        id = "plain"
        label = "Plain"

    assert Plain.process_lifetime_modules == ()


def test_install_routes_is_a_noop_by_default():
    Widgets.__module__ = "pkg.capabilities.widgets"
    app = Starlette()

    Widgets().install_routes(app)

    assert app.routes == []


def test_on_startup_is_a_noop_by_default():
    Widgets.__module__ = "pkg.capabilities.widgets"

    assert Widgets().on_startup() is None
