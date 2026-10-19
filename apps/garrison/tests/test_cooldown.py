"""Gateway failures must not suppress healthy gateways of the same provider."""

import pytest

from src.llm import cooldown


@pytest.fixture(autouse=True)
def clean_cooldowns():
    cooldown.reset()
    yield
    cooldown.reset()


def test_gateway_cooldown_is_isolated_and_reset_clears_all():
    cooldown.start_cooldown(cooldown.gateway_key("anthropic", "openrouter"), 30)
    assert cooldown.is_in_cooldown("anthropic:openrouter")
    assert not cooldown.is_in_cooldown("anthropic:claude")
    cooldown.start_cooldown("openai", 10)
    assert cooldown.is_in_cooldown("openai")
    cooldown.reset()
    assert cooldown.seconds_remaining("anthropic:openrouter") == 0
    assert cooldown.seconds_remaining("openai") == 0
