"""Shared catalog; startup owns its background task."""

from pathlib import Path
from urllib.parse import urlsplit

from src.citadel_auth import ServiceCatalog, data_dir
from src.config import settings
from src.services.service_auth import keyring
from src.services.connections import _origin

catalog = ServiceCatalog(keyring, settings.treasury_url, cache_path=data_dir(Path(__file__).resolve().parents[1]) / "catalog_cache.json")


def require_internal_origin(address: str, audience: str) -> None:
    """Send Citadel assertions only to the audience's active catalog origin."""
    try:
        parsed = urlsplit(address)
        valid = parsed.username is None and parsed.password is None and _origin(address) == _origin(catalog.url(audience))
    except (KeyError, ValueError):
        valid = False
    if not valid:
        raise ValueError("The signed connection address must match its audience in the Treasury catalog.")
