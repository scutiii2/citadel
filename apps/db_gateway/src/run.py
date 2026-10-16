"""Start the db_gateway: `python -m src.run`."""

from __future__ import annotations

import logging

import uvicorn

from src.api import create_app
from src.auth import load_token
from src.backends.factory import build_backend
from src.config import load_config, load_connections
from src.registry import ConnectionRegistry, InstanceManager

log = logging.getLogger("db_gateway")


def build_app():
    config = load_config()
    connections = load_connections(config.default_cache)
    registry = ConnectionRegistry(connections.connections, build_backend)
    manager = InstanceManager(connections.instances, registry)
    log.info("instances: %s", ", ".join(connections.instances) or "none")
    return create_app(manager, load_token()), config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app, config = build_app()
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
