"""Signed Armory Admin and Stronghold metadata endpoints for Instance Brain."""

import asyncio
import sqlite3

from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.capabilities.obsidian.utils import brain_resolver
from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError
from src.capabilities.obsidian.utils.instance_brain import ConnectionInput, DisableInput, InstanceBrainStore
from src.citadel_auth import current_caller, current_requester
from src.services.service_auth import install_auth


class BrainRoutes:
    def __init__(self, store: InstanceBrainStore):
        self.store = store

    async def view(self, request: Request):
        return await self.respond("portcullis", self.store.view)

    async def save(self, request: Request):
        return await self.respond("portcullis", self._save, request, ConnectionInput)

    async def disable(self, request: Request):
        return await self.respond("portcullis", self._disable, request, DisableInput)

    async def test(self, request: Request):
        return await self.respond("portcullis", self._test, request, ConnectionInput)

    async def status(self, request: Request):
        return await self.respond("portcullis", self._status)

    async def destination(self, request: Request):
        return await self.respond("stronghold", self._destination)

    def _replace(self, update):
        result, previous_generation = update()
        from src.capabilities.obsidian.utils.brain_indexes import indexes

        indexes.retire("", "instance", generation=previous_generation)
        return result

    def _save(self, body: ConnectionInput):
        return self._replace(lambda: self.store.save(body))

    def _disable(self, body: DisableInput):
        return self._replace(lambda: self.store.disable(body.expected_revision))

    def _destination(self):
        settings = brain_resolver.settings
        return self.store.destination(
            legacy_writable=bool(settings.obsidian_allow_write and settings.obsidian_base_url and settings.obsidian_api_key),
        )

    @staticmethod
    def _probe(snapshot):
        try:
            brain_resolver.gateway(snapshot).list("")
        except ObsidianGatewayError as error:
            # A vault refusal is a settings error, independent of the admin's Citadel session.
            raise ObsidianGatewayError(str(error), status=400) from None

    def _test(self, body: ConnectionInput):
        self._probe(self.store.candidate(body))
        return {"status": "connected", "message": "Read-only connection test succeeded"}

    def _status(self):
        from src.capabilities.obsidian.utils.brain_indexes import indexes

        snapshot = self.store.snapshot()
        self._probe(snapshot)
        return {"status": "connected", "index_status": indexes.status(snapshot)}

    async def respond(self, caller, operation, request=None, model: type[BaseModel] | None = None):
        service = current_caller()
        if service is None or service.name != caller or current_requester() is None:
            return JSONResponse({"error": "Authorized requester required"}, status_code=403)
        try:
            if caller == "portcullis":
                await brain_resolver.authorize_management()
            args = ()
            if model is not None:
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > 32_000:
                        return JSONResponse({"error": "Brain request too large"}, status_code=413)
                args = (model.model_validate_json(raw),)
            return JSONResponse(await asyncio.to_thread(operation, *args))
        except ValidationError as error:
            messages = [item["msg"] for item in error.errors(include_input=False, include_context=False)
                        if item["type"] == "value_error"]
            return JSONResponse({"error": messages[0] if messages else "Invalid brain settings"}, status_code=422)
        except ObsidianGatewayError as error:
            return JSONResponse({"error": str(error)}, status_code=error.status or 503)
        except (OSError, ValueError, sqlite3.Error):
            return JSONResponse({"error": "Instance Brain is unavailable"}, status_code=503)


def install(app, store: InstanceBrainStore):
    install_auth(app)
    routes = BrainRoutes(store)
    app.add_route("/admin/brain", routes.view, methods=["GET"])
    app.add_route("/admin/brain", routes.save, methods=["PUT"])
    app.add_route("/admin/brain/test", routes.test, methods=["POST"])
    app.add_route("/admin/brain/status", routes.status, methods=["GET"])
    app.add_route("/admin/brain/disable", routes.disable, methods=["POST"])
    app.add_route("/brains/destination", routes.destination, methods=["GET"])
