import importlib.util

import pytest
from fastapi import HTTPException

from src.brain.access import need


def test_need_refuses_a_missing_permission():
    with pytest.raises(HTTPException) as refused:
        need(set(), "brain.global.write")
    assert refused.value.status_code == 403


def test_need_allows_a_granted_permission():
    need({"brain.global.write"}, "brain.global.write")


@pytest.mark.parametrize("module", ["src.brains", "src.notes"])
def test_the_legacy_packages_are_gone(module):
    assert importlib.util.find_spec(module) is None
