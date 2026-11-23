import pytest

from src.gateway.conversation.failure import scrub, upstream_error


def test_scrub_hides_secrets_and_shortens():
    assert scrub("bad key sk-secret here", ["sk-secret"]) == "bad key *** here"
    assert len(scrub("x " * 1000, [])) <= 500


@pytest.mark.parametrize("status,text,expect", [
    (402, "pay up", (402, "quota")),
    (400, "Your credit balance is too low", (402, "quota")),
    (429, "You exceeded your current quota", (402, "quota")),
    (429, "slow down", (429, "rate_limit")),
    (401, "nope", (502, "auth")),
    (403, "nope", (502, "auth")),
    (500, "boom", (502, "unavailable")),
    (529, "overloaded", (502, "unavailable")),
    (400, "bad field", (422, None)),
    (404, "no such model", (422, None)),
    (413, "big", (413, None)),
    (418, "teapot", (502, None)),
])
def test_status_mapping(status, text, expect):
    error = upstream_error(status, text)
    assert (error.status, error.kind) == expect


def test_retry_after_is_copied_and_limited():
    assert upstream_error(429, "x", "7").retry_after == 7
    assert upstream_error(429, "x", "9999").retry_after == 60
    assert upstream_error(429, "x", None).retry_after == 1


def test_message_never_holds_the_secret():
    assert "sk-123" not in upstream_error(401, "key sk-123 rejected", secrets=["sk-123"]).message
