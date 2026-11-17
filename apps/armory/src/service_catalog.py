"""Shared catalog; startup owns its background task."""

from pathlib import Path

from src.citadel_auth import ServiceCatalog, data_dir
from src.config import settings
from src.services.service_auth import keyring

catalog = ServiceCatalog(keyring, settings.treasury_url, cache_path=data_dir(Path(__file__).resolve().parents[1]) / "catalog_cache.json")
