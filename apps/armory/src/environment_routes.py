"""HTTP endpoints for the deployment values an administrator edits while Armory runs; plain routes beside the MCP surface.
GET /admin/tuning, PUT and DELETE /admin/tuning/{pdf_merger|media_downloader} read, change and reset the caps and lifetimes of the PDF and video capabilities.
GET/PUT /admin/email read and change the SMTP settings (the password only as `has_password`).
GET /admin/environment lists every setting (a secret only as `has_value`); PUT /admin/environment takes
``{field: value | null}`` (null puts the `.env` or default value back) and answers 400 with the reason if any is refused."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import config, environment_settings
from src.services import app_config, capability_tuning, tool_policy


def _validator(name: str):
    if name == "pdf_merger":
        from src.capabilities.pdf_merger.utils.pdf_runtime import validate_tuning
    else:
        from src.capabilities.media_downloader.utils.media_downloads import validate_tuning
    return validate_tuning


def tuning_view(path) -> dict[str, object]:
    """The caps and lifetimes of the PDF and video capabilities, with whether each was changed from the defaults."""
    return {name: {**capability_tuning.document(path, name), "stored": capability_tuning.is_stored(path, name)}
            for name in capability_tuning.DEFAULTS}


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
    async def get_tuning(request: Request) -> JSONResponse:
        return JSONResponse(tuning_view(config.settings.settings_db_path))

    async def put_tuning(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        try:
            changes = await request.json()
        except Exception:  # noqa: BLE001 - malformed JSON is a 400, not a 500
            changes = None
        try:
            if name not in capability_tuning.DEFAULTS:
                raise capability_tuning.TuningError(f"Unknown capability: {name}.")
            capability_tuning.save(config.settings.settings_db_path, name, changes, _validator(name))
        except capability_tuning.TuningError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        except OSError as error:
            return JSONResponse({"error": f"Could not save the limits ({error.strerror or error})"}, status_code=409)
        return JSONResponse({**tuning_view(config.settings.settings_db_path), "applies": "next start"})

    async def reset_tuning(request: Request) -> JSONResponse:
        try:
            capability_tuning.reset(config.settings.settings_db_path, request.path_params["name"])
        except capability_tuning.TuningError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        return JSONResponse({**tuning_view(config.settings.settings_db_path), "applies": "next start"})

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

    async def get_tool_approval(request: Request) -> JSONResponse:
        path = config.settings.settings_db_path
        return JSONResponse({"force_tool_approval": tool_policy.forced(path), "stored": tool_policy.is_stored(path)})

    async def put_tool_approval(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - malformed JSON is a 400, not a 500
            body = None
        value = body.get("value") if isinstance(body, dict) else None
        if not isinstance(value, bool):
            return JSONResponse({"error": "body must be {\"value\": true or false}"}, status_code=400)
        try:
            before = tool_policy.set_forced(config.settings.settings_db_path, value)
        except OSError as error:
            return JSONResponse({"error": f"Could not save the setting ({error.strerror or error})"}, status_code=409)
        return JSONResponse({"force_tool_approval": value, "before": before})

    app.add_route("/admin/tool-approval", get_tool_approval, methods=["GET"])
    app.add_route("/admin/tool-approval", put_tool_approval, methods=["PUT"])
    app.add_route("/admin/environment", get_environment, methods=["GET"])
    app.add_route("/admin/environment", put_environment, methods=["PUT"])
    app.add_route("/admin/tuning", get_tuning, methods=["GET"])
    app.add_route("/admin/tuning/{name}", put_tuning, methods=["PUT"])
    app.add_route("/admin/tuning/{name}", reset_tuning, methods=["DELETE"])
    app.add_route("/admin/email", get_email, methods=["GET"])
    app.add_route("/admin/email", put_email, methods=["PUT"])
