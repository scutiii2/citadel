"""Read-only SMTP readiness check for Ember invitation delivery."""

from pathlib import Path

from src.config import settings
from src.services import app_config, capability_registry
from src.services.email.send import SMTP_SECURITY_MODES, open_smtp


def check_email_health(config_path: Path | None = None) -> tuple[bool, str]:
    """Return the first readiness failure without sending mail."""
    try:
        enabled = capability_registry.is_enabled("email")
    except KeyError:
        enabled = False
    if not enabled:
        return False, "The Email capability is switched off in Armory."

    path = config_path if config_path is not None else settings.settings_db_path
    try:
        if app_config.email_document(path) is None:
            return False, "Email is not set up. Fill in the Email page of Armory Admin."
        config = app_config.load_email_config(path)
        if config.security not in SMTP_SECURITY_MODES:
            raise ValueError("Unknown SMTP security mode")
    except Exception:
        return False, "The email settings are invalid. Check the Email page of Armory Admin."

    try:
        with open_smtp(config):
            pass
    except Exception:
        return False, "Armory could not log in to the mail server. Check the Email page of Armory Admin."

    return True, "Email is ready."
