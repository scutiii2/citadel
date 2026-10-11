"""Serve the game's built UI with an Ember-only frame ancestor."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from src.config import GameHostConfigParser


class UiMount:
    def __init__(self, dist: Path, ember_origin: str) -> None:
        self._dist = dist.resolve()
        self._assets = self._dist / "assets"
        self._manifest = Path(__file__).resolve().parent.parent / "manifest.json"
        origin = GameHostConfigParser({"ember_origin": ember_origin}).url("ember_origin", origin=True)
        self._headers = {
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors " + origin,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        }

    def _not_found(self) -> HTTPException:
        return HTTPException(404, "Not Found", headers=self._headers)

    def _resolve(self, path: Path, *, within: Path) -> Path:
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(self._dist) or not resolved.is_relative_to(within) or not resolved.is_file():
                raise self._not_found()
        except (OSError, RuntimeError, ValueError) as error:
            raise self._not_found() from error
        return resolved

    def asset(self, file_path: str) -> FileResponse:
        if "\\" in file_path or any(part in (".", "..") for part in file_path.split("/")):
            raise self._not_found()
        resolved = self._resolve(self._assets / file_path, within=self._assets)
        return FileResponse(resolved, headers=self._headers)

    def page(self, path: str) -> FileResponse | PlainTextResponse:
        if any(path == prefix or path.startswith(prefix + "/") for prefix in ("ascension", "session", "health")):
            raise self._not_found()
        # Missing file requests (including a normalised /assets/../config.py)
        # are never turned into SPA routes. Route names without suffixes fall back.
        if "\\" in path or any(part.startswith(".") for part in path.split("/") if part) or Path(path).suffix:
            raise self._not_found()
        index = self._dist / "index.html"
        if not index.is_file():
            return PlainTextResponse("UI not built: run npm --prefix web run build", status_code=503, headers=self._headers)
        return FileResponse(self._resolve(index, within=self._dist), media_type="text/html", headers=self._headers)

    def mount(self, app: FastAPI) -> None:
        """Mount after the game API so the catch-all is always last."""
        @app.get("/manifest.json")
        def manifest():
            return FileResponse(self._manifest, media_type="application/json", headers=self._headers)

        @app.get("/assets/{file_path:path}")
        def asset(file_path: str):
            return self.asset(file_path)

        @app.get("/{path:path}")
        def page(path: str):
            return self.page(path)
