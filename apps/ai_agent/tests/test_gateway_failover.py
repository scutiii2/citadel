"""Route failures using SDK identity/status, without exposing gateway messages."""

import httpx
import anthropic
import openai
import pytest

from src.llm import cooldown, gateway_failover as failover


def sdk_error(sdk, status, message="failure", headers=None):
    request = httpx.Request("POST", "https://fake.invalid")
    response = httpx.Response(status, request=request, headers=headers)
    cls = {400: sdk.BadRequestError, 401: sdk.AuthenticationError,
           403: sdk.PermissionDeniedError, 429: sdk.RateLimitError,
           500: sdk.InternalServerError}.get(status, sdk.APIStatusError)
    return cls(message, response=response, body=None)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    cooldown.reset()
    monkeypatch.setattr(failover, "read_section", lambda *args, **kwargs: {})
    yield
    cooldown.reset()


@pytest.mark.parametrize("sdk", [anthropic, openai])
@pytest.mark.parametrize("status,message,want", [
    (429, "slow", "rate_limit"), (402, "pay", "quota"),
    (400, "INSUFFICIENT credit", "quota"), (429, "Quota used", "quota"),
    (401, "key", "auth"), (403, "denied", "auth"),
    (500, "failure", "unavailable"), (529, "overloaded", "unavailable"),
    (400, "wrong option", None), (404, "missing model", None),
])
def test_classification(sdk, status, message, want):
    result = failover.classify(sdk_error(sdk, status, message))
    assert (result.value if result else None) == want


@pytest.mark.parametrize("sdk", [anthropic, openai])
@pytest.mark.parametrize("name", ["APIConnectionError", "APITimeoutError"])
def test_transport_errors(sdk, name):
    error = getattr(sdk, name)(request=httpx.Request("POST", "https://fake.invalid"))
    assert failover.classify(error).value == "unavailable"


@pytest.mark.parametrize("error", [ValueError("quota"), TimeoutError(), RuntimeError("overloaded")])
def test_non_sdk_errors_are_not_retried(error):
    assert failover.classify(error) is None


def test_route_skips_missing_credentials_and_cooldowns_and_never_flaps():
    cooldown.start_cooldown("anthropic:primary", 60)
    route = failover.GatewayRoute.for_turn("anthropic", "primary", ["missing", "backup", "last"],
                                          lambda name: name != "missing")
    assert route.current == "backup"
    switch = route.advance(sdk_error(anthropic, 429, headers={"retry-after": "17"}))
    assert (switch.from_gateway, switch.to_gateway, switch.reason) == ("backup", "last", "rate_limit")
    assert 16 < cooldown.seconds_remaining("anthropic:backup") <= 17
    assert route.switches == [switch]
    assert route.advance(sdk_error(anthropic, 402)) is None
    assert cooldown.is_in_cooldown("anthropic:last")


def test_primary_recovers_on_next_turn(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cooldown.time, "monotonic", lambda: clock[0])
    route = failover.GatewayRoute.for_turn("openai", "primary", ["backup"], lambda _: True)
    route.advance(sdk_error(openai, 500))
    assert route.current == "backup"
    assert failover.GatewayRoute.for_turn("openai", "primary", ["backup"], lambda _: True).current == "backup"
    clock[0] += 31
    assert failover.GatewayRoute.for_turn("openai", "primary", ["backup"], lambda _: True).current == "primary"


def test_all_cooling_still_tries_primary_and_nonfailure_has_no_effect():
    for name in ("primary", "backup"):
        cooldown.start_cooldown("openai:" + name, 60)
    route = failover.GatewayRoute.for_turn("openai", "primary", ["backup"], lambda _: True)
    assert route.current == "primary"
    cooldown.reset()
    assert route.advance(ValueError("credit")) is None
    assert not route.switches
    assert not cooldown.is_in_cooldown("openai:primary")


@pytest.mark.parametrize("kind,seconds", [("rate_limit", 60), ("quota", 3600),
                                          ("auth", 3600), ("unavailable", 30)])
def test_default_cooldowns(kind, seconds):
    assert failover.cooldown_seconds(failover.FailureKind(kind), sdk_error(openai, 500)) == seconds


def test_configured_cooldown(monkeypatch):
    monkeypatch.setattr(failover, "read_section", lambda *args, **kwargs: {"quota_cooldown_seconds": 42})
    assert failover.cooldown_seconds(failover.FailureKind.quota, sdk_error(openai, 402)) == 42
