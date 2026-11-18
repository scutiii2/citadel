"""Stronghold's settings: host and port from `configs/config_app.json` (or `STRONGHOLD_CONFIG`), addresses from the
environment, and the usage limits and price table from the settings database (edited in Stronghold Admin).
A missing file means defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from src.citadel_auth import apply_root_env, data_dir as _data_dir

from src.usage import admin_settings
from src.usage.settings import PricingSettings, UsageSettings

PROJECT_DIR = Path(__file__).resolve().parent.parent
apply_root_env(PROJECT_DIR)  # the Citadel root .env overrides this service's .env


@dataclass(frozen=True)
class Settings:
    # Where Stronghold listens. STRONGHOLD_HOST and STRONGHOLD_PORT win over the file (Compose sets them).
    host: str = "127.0.0.1"
    port: int = 29650
    treasury_url: str = "http://127.0.0.1:29602"
    advertise_url: str | None = None
    # Legion's registry of running agents: the file its supervisor writes, or its /registry URL (wins when set).
    agents_registry_path: Path = _data_dir(PROJECT_DIR.parent / "legion") / "agent_registry.json"
    agents_registry_url: str | None = None
    # Stronghold's own instance and connection in Treasury.
    db_instance: str = "stronghold"
    db_connection: str = "stronghold"
    data_dir: Path = _data_dir(PROJECT_DIR)
    usage: UsageSettings = field(default_factory=UsageSettings)
    pricing: PricingSettings = field(default_factory=PricingSettings)


def load_settings() -> Settings:
    path = Path(os.getenv("STRONGHOLD_CONFIG") or PROJECT_DIR / "configs" / "config_app.json")
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    base = Settings()
    data_dir = Path(os.getenv("STRONGHOLD_DATA_DIR") or base.data_dir)
    usage, pricing = admin_settings.load(data_dir / "settings.db")
    return Settings(
        host=os.getenv("STRONGHOLD_HOST") or str(raw.get("host", base.host)),
        port=int(os.getenv("STRONGHOLD_PORT") or raw.get("port", base.port)),
        treasury_url=os.getenv("TREASURY_URL") or raw.get("treasury_url") or base.treasury_url,
        advertise_url=raw.get("advertise_url") or None,
        agents_registry_path=Path(os.getenv("AGENTS_REGISTRY_PATH") or base.agents_registry_path),
        agents_registry_url=os.getenv("AGENTS_REGISTRY_URL") or None,
        data_dir=data_dir,
        usage=usage,
        pricing=pricing,
    )
