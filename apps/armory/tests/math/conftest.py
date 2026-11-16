"""Every test here starts real worker processes, so the folder is `slow` (skipped unless run with -m "")."""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/math/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.slow)
