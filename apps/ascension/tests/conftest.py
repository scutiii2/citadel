"""Shared fixtures. Tests never read the real configs/ or .env files."""

from pathlib import Path

import pytest

from src.config import AppConfig, load_config

EXAMPLE_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "config_app.json.example"


@pytest.fixture
def config() -> AppConfig:
    return load_config(EXAMPLE_CONFIG)



def signed_in(app, owner: str) -> dict[str, str]:
    """Issue an app-local session for HTTP tests; owners stay text identifiers."""
    token = app.state.sessions.open(owner)
    return {"Authorization": f"Bearer {token}"}
