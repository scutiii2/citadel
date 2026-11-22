"""Durable ticket settings, shared with the service's admin routes."""

from pathlib import Path

from src.citadel_auth import settings_store
from src.tickets.config import TicketConfig, load_ticket_config

TABLE = "ticket_settings"
KEY = "tickets"


def load(path: Path) -> TicketConfig:
    return load_ticket_config(settings_store.read_all(path, TABLE).get(KEY))


def save(path: Path, config: TicketConfig) -> None:
    settings_store.put(path, TABLE, KEY, config.document())
