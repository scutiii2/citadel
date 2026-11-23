from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from src.services import capability_registry
from src.services.app_config import EmailConfig


@pytest.fixture
def probe(tmp_path, monkeypatch):
    enabled = MagicMock(return_value=True)
    document = MagicMock(return_value={})
    config = EmailConfig("smtp.example.com", 587, "sender@example.com", password="test-password")
    load = MagicMock(return_value=config)
    smtp = MagicMock()
    ssl = MagicMock()
    monkeypatch.setattr(capability_registry, "is_enabled", enabled)
    monkeypatch.setattr("src.services.app_config.email_document", document)
    monkeypatch.setattr("src.services.app_config.load_email_config", load)
    monkeypatch.setattr("smtplib.SMTP", smtp)
    monkeypatch.setattr("smtplib.SMTP_SSL", ssl)

    def check():
        from src.services.email.health import check_email_health

        return check_email_health(tmp_path / "test-settings.db")

    return check, enabled, document, load, smtp, ssl


@pytest.mark.parametrize("missing", [False, True])
def test_disabled_email_wins_over_missing_settings(probe, missing):
    check, enabled, document, _, smtp, ssl = probe
    enabled.return_value = False
    if missing:
        enabled.side_effect = KeyError("email")
    assert check() == (False, "The Email capability is switched off in Armory.")
    document.assert_not_called()
    smtp.assert_not_called()
    ssl.assert_not_called()


def test_missing_email_document(probe):
    check, _, document, load, smtp, ssl = probe
    document.return_value = None
    assert check() == (False, "Email is not set up. Fill in the Email page of Armory Admin.")
    load.assert_not_called()
    smtp.assert_not_called()
    ssl.assert_not_called()


@pytest.mark.parametrize("read_error", [False, True])
def test_invalid_email_settings(probe, read_error):
    check, _, _, load, smtp, ssl = probe
    if read_error:
        load.side_effect = ValueError("private configuration details")
    else:
        load.return_value = replace(load.return_value, security="invalid")
    assert check() == (False, "The email settings are invalid. Check the Email page of Armory Admin.")
    smtp.assert_not_called()
    ssl.assert_not_called()


def test_login_error_uses_fixed_reason_and_closes_connection(probe):
    check, _, _, _, smtp, _ = probe
    client = smtp.return_value
    server = client.__enter__.return_value
    server.login.side_effect = RuntimeError("private error containing test-password")
    assert check() == (False, "Armory could not log in to the mail server. Check the Email page of Armory Admin.")
    client.__exit__.assert_called_once()
    server.sendmail.assert_not_called()


@pytest.mark.parametrize("password", ["", "test-password"])
def test_health_authenticates_when_needed_and_sends_nothing(probe, password):
    check, _, _, load, smtp, _ = probe
    load.return_value = replace(load.return_value, password=password)
    client = smtp.return_value
    server = client.__enter__.return_value
    assert check() == (True, "Email is ready.")
    smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
    server.starttls.assert_called_once_with()
    if password:
        server.login.assert_called_once_with("sender@example.com", password)
    else:
        server.login.assert_not_called()
    server.mail.assert_not_called()
    server.sendmail.assert_not_called()
    client.__exit__.assert_called_once()
