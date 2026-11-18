"""Start Stronghold: `python -m src.run`."""

from __future__ import annotations

import logging

import uvicorn

from src.api import create_app
from src.config import load_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
