"""One catalog shared by Legion startup and MCP connections."""

from src.citadel_auth import ServiceCatalog, data_dir
from src.runtime import config_files, gateway_settings, internal_auth

catalog = ServiceCatalog(internal_auth.keyring, gateway_settings.treasury_address(),
                         cache_path=data_dir(config_files.CONFIGS_DIR.parent) / "catalog_cache.json")
