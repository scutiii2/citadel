"""HTTP endpoints for the deployment values an administrator edits while Armory runs; plain routes beside the MCP surface.
GET/PUT /admin/email read and change the SMTP settings (the password only as `has_password`).
GET /admin/environment lists every setting (a secret only as `has_value`); PUT /admin/environment takes
``{field: value | null}`` (null puts the `.env` or default value back) and answers 400 with the reason if any is refused."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import config, environment_settings
from src.services import app_config


def email_view(path) -> dict[str, object]:
    """The saved SMTP settings; the password is only reported as `has_password`."""
    document = app_config.email_document(path)
    if document is None:
        return {"configured": False}
    return {
        "configured": True,
        "smtp_server": document.get("smtp_server", ""),
        "smtp_port": document.get("smtp_port"),
        "security": document.get("security", ""),
        "from": document.get("from", ""),
        "to": document.get("to", []),
        "allowed_recipient_domains": document.get("allowed_recipient_domains", []),
        "has_password": bool(document.get("password")),
    }


def install_environment_routes(app: Starlette) -> None:
    async def get_email(request: Request) -> JSONResponse:
        return JSONResponse(email_view(config.settings.settings_db_path))

    async def put_email(request: Request) -> JSONResponse:
        try:
            changes = await request.json()
        except Exception:  # noqa: BLE001 - malformed JSON is a 400, not a 500
            changes = None
        if not isinstance(changes, dict) or not changes:
            return JSONResponse({"error": "body must be a JSON object with at least one setting"}, status_code=400)
        try:
            app_config.save_email_settings(config.settings.settings_db_path, changes)
        except (KeyError, ValueError) as error:
            return JSONResponse({"error": str(error).strip("'\"")}, status_code=400)
        except OSError as error:
            return JSONResponse({"error": f"Could not save the email settings ({error.strerror or error})"}, status_code=409)
        return JSONResponse(email_view(config.settings.settings_db_path))

    async def get_environment(request: Request) -> JSONResponse:
        return JSONResponse(environment_settings.view(config.settings, config.settings.settings_db_path))

    async def put_environment(request: Request) -> JSONResponse:
        try:
            changes = await request.json()
        except Exception:  # noqa: BLE001 - malformed JSON is a 400, not a 500
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        if not isinstance(changes, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        try:
            restart = environment_settings.update(
                config.settings, config.Settings(), config.settings.settings_db_path, changes
            )
        except environment_settings.SettingError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        except OSError as error:
            return JSONResponse({"error": f"Could not save the settings ({error.strerror or error})"}, status_code=409)
        body = environment_settings.view(config.settings, config.settings.settings_db_path)
        return JSONResponse({**body, "restart": restart})

    app.add_route("/admin/environment", get_environment, methods=["GET"])
    app.add_route("/admin/environment", put_environment, methods=["PUT"])
    app.add_route("/admin/email", get_email, methods=["GET"])
    app.add_route("/admin/email", put_email, methods=["PUT"])
