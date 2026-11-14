"""Start Stronghold: `python -m src.run`."""

from __future__ import annotations

import logging
import os

import uvicorn

from src.api import create_app
from src.auth import load_token

DEFAULT_PORT = 29650


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.getenv("STRONGHOLD_HOST", "127.0.0.1")
    port = int(os.getenv("STRONGHOLD_PORT", str(DEFAULT_PORT)))
    uvicorn.run(create_app(load_token()), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
