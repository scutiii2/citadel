"""Stronghold's settings: addresses from the environment, feature blocks from a JSON file.

The file is `configs/config_app.json` (or `STRONGHOLD_CONFIG`). A missing file means defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from src.calendar.settings import CalendarSettings
from src.usage.settings import PricingSettings, UsageSettings

PROJECT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    portcullis_url: str = "http://127.0.0.1:29601"
    db_gateway_url: str = "http://127.0.0.1:29602"
    armory_url: str = "http://127.0.0.1:29600"
    # Legion's registry of running agents: the file its supervisor writes, or its /registry URL (wins when set).
    agents_registry_path: Path = PROJECT_DIR.parent / "legion" / ".data" / "agent_registry.json"
    agents_registry_url: str | None = None
    # Stronghold's own instance and connection in Treasury.
    db_instance: str = "stronghold"
    db_connection: str = "stronghold"
    data_dir: Path = PROJECT_DIR / ".data"
    calendar: CalendarSettings = field(default_factory=CalendarSettings)
    usage: UsageSettings = field(default_factory=UsageSettings)
    pricing: PricingSettings = field(default_factory=PricingSettings)


def load_settings() -> Settings:
    path = Path(os.getenv("STRONGHOLD_CONFIG") or PROJECT_DIR / "configs" / "config_app.json")
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    base = Settings()
    return Settings(
        portcullis_url=os.getenv("PORTCULLIS_URL") or base.portcullis_url,
        db_gateway_url=os.getenv("DB_GATEWAY_URL") or base.db_gateway_url,
        armory_url=os.getenv("ARMORY_URL") or base.armory_url,
        agents_registry_path=Path(os.getenv("AGENTS_REGISTRY_PATH") or base.agents_registry_path),
        agents_registry_url=os.getenv("AGENTS_REGISTRY_URL") or None,
        data_dir=Path(os.getenv("STRONGHOLD_DATA_DIR") or base.data_dir),
        calendar=CalendarSettings.from_config(raw.get("calendar", {})),
        usage=UsageSettings.from_config(raw.get("usage", {})),
        pricing=PricingSettings.from_config(raw.get("pricing", {})),
    )
