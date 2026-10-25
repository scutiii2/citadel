"""The generator tools' `email_to`: the value goes to the inbox and never into the result."""

from __future__ import annotations

import pytest

from src.capabilities.generator import domain
from src.services.email import delivery as email_delivery

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict] = []

    def fake_deliver(to, subject, body_text, **kwargs):
        calls.append({"to": to, "subject": subject, "body": body_text, **kwargs})
        return "<id@example>"

    monkeypatch.setattr(email_delivery, "deliver_email", fake_deliver)
    return calls


def test_pin_is_emailed_and_left_out_of_the_result(sent):
    result = domain.generate_pin(6, email_to="me@example.com")

    assert result.pin is None
    assert result.emailed_to == "me@example.com"
    assert len(sent) == 1 and sent[0]["to"] == ["me@example.com"]
    digits = sent[0]["body"].split("\n\n")[1]
    assert digits.isdigit() and len(digits) == 6
    assert digits not in result.message and digits not in result.model_dump_json()


def test_password_and_passphrase_are_emailed(sent):
    password = domain.generate_password(email_to="a@example.com, b@example.com")
    phrase = domain.generate_passphrase(email_to="a@example.com")

    assert password.password is None and password.emailed_to == "a@example.com, b@example.com"
    assert sent[0]["to"] == ["a@example.com", "b@example.com"]
    assert phrase.passphrase is None and len(sent) == 2


def test_totp_secret_hides_both_the_secret_and_the_uri(sent):
    result = domain.generate_totp_secret("Ember", "me", email_to="me@example.com")

    assert result.secret is None and result.otpauth_uri is None
    assert "otpauth://totp/" in sent[0]["body"]


def test_totp_code_is_emailed(sent):
    result = domain.get_totp_code(RFC_SECRET, at=59, email_to="me@example.com")

    assert result.code is None and "287082" in sent[0]["body"] and "287082" not in result.message


def test_no_email_to_returns_the_value_and_sends_nothing(sent):
    result = domain.generate_pin(6)

    assert result.pin and result.emailed_to is None and sent == []


def test_bad_address_fails_before_anything_is_sent(sent):
    with pytest.raises(ValueError, match="valid email addresses"):
        domain.generate_pin(6, email_to="not-an-address")
    with pytest.raises(ValueError, match="control characters"):
        domain.generate_pin(6, email_to="a@example.com\nBcc: x@example.com")
    assert sent == []


def test_failed_delivery_never_returns_the_value(monkeypatch):
    def boom(*args, **kwargs):
        raise email_delivery.EmailUnavailable("email capability is disabled")

    monkeypatch.setattr(email_delivery, "deliver_email", boom)

    with pytest.raises(email_delivery.EmailUnavailable):
        domain.generate_pin(6, email_to="me@example.com")
