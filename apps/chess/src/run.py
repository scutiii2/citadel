"""Start the chess backend: `python -m src.run`."""

from __future__ import annotations

import logging

import uvicorn

from src.api import create_app
from src.auth import load_token
from src.config import load_config
from src.games.registry import build_games
from src.opponent.engine_picker import EnginePicker
from src.opponent.laya_client import LayaClient, LayaError
from src.opponent.laya_picker import LayaPicker
from src.opponent.variety_picker import VarietyPicker
from src.sessions import SessionStore

log = logging.getLogger("chess")


def build_app():
    config = load_config()
    games = build_games()
    laya = LayaClient(timeout=config.laya_timeout_seconds)
    if laya.is_available():
        try:
            laya.prepare()
            log.info("Laya loaded")
        except LayaError as error:
            log.warning("Laya could not be loaded; the laya picker will use the engine: %s", error)
    else:
        log.info("Laya is not installed; the laya picker will use the engine")
    pickers = {p.name: p for p in (EnginePicker(), VarietyPicker(), LayaPicker(laya))}
    store = SessionStore(games, pickers, config)
    return create_app(store, games, load_token()), config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app, config = build_app()
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
