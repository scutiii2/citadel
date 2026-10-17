"""Remote single-choice classifier: typesafe-ai/jev through Vercel AI Gateway.

One question at a time: pick one of the named options and say how sure (0-100).
It never writes text or calls tools. It is used where the small local model is
not enough: Laya's uncertain triage answers and inputs too long for Laya
(llm/laya_provider.py). Every failure is a ClassifierError, which a caller
treats as "no answer" and carries on without.

Off by default. A feature runs only when config_tuning.json's `classifier`
section turns it on and AI_GATEWAY_API_KEY is set (in `.env`). The text sent to
it leaves this machine, and each call is billed by the gateway.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from src.core.catalog import catalog
from src.core.config_files import TUNING_PATH, read_section

DEFAULT_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
DEFAULT_MODEL = "typesafe-ai/jev"
KEY_ENV = "AI_GATEWAY_API_KEY"

_SECTION = "classifier"
_KNOWN = {"url", "model", "timeout_seconds", "max_input_chars", "triage_fallback", "auto_tier"}
_AUTO_TIER_KNOWN = {"enabled", "min_confidence", "tiers"}

# How hard a request is, as the ClaudeRouters size classifier names it.
SIZE_CRITERIA = {
    "tiny": "a lookup, a rename, a one-line answer",
    "everyday": "a normal email, post, or short document",
    "large": "a multi-step build, research, a full report",
    "hardest": "strategy, or anything where a wrong call is expensive",
}
DEFAULT_SIZE_TIERS = (("tiny", "light"), ("everyday", "light"), ("large", "standard"), ("hardest", "heavy"))


class ClassifierError(Exception):
    """The classifier gave no usable answer; the message says why."""


@dataclass(frozen=True)
class AutoTierSettings:
    """Choosing a turn's model tier from how hard the question looks (llm/auto_tier.py)."""

    enabled: bool = False
    # Jev's confidence (0-100) needed before its size is used; below it the default model runs.
    min_confidence: int = 60
    # request size -> model tier; the agent's own min_tier/max_tier still clamp the result.
    tiers: tuple[tuple[str, str], ...] = DEFAULT_SIZE_TIERS


@dataclass(frozen=True)
class ClassifierSettings:
    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 3.0
    # Longest text sent for a typed question. Laya reads at most 4000 characters;
    # Jev has a larger window, so longer texts go to it instead.
    max_input_chars: int = 16_000
    # Re-ask Jev about the answers Laya is unsure of, and about texts Laya cannot read.
    triage_fallback: bool = False
    auto_tier: AutoTierSettings = AutoTierSettings()


@catalog
def settings() -> ClassifierSettings:
    """The `classifier` section of config_tuning.json over the defaults above (all off)."""
    return _load_settings()


@lru_cache(maxsize=1)
def _load_settings() -> ClassifierSettings:
    raw = read_section(TUNING_PATH, _SECTION, {})
    if not isinstance(raw, dict):
        raise ValueError(f"config_tuning.json {_SECTION} must be an object")
    unknown = set(raw) - _KNOWN
    if unknown:
        raise ValueError(f"config_tuning.json {_SECTION} has unknown field(s): {', '.join(sorted(unknown))}")
    base = ClassifierSettings()
    for field in ("url", "model"):
        if not isinstance(raw.get(field, getattr(base, field)), str) or not raw.get(field, getattr(base, field)).strip():
            raise ValueError(f"config_tuning.json {_SECTION}.{field} must be a non-empty string")
    timeout = raw.get("timeout_seconds", base.timeout_seconds)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise ValueError(f"config_tuning.json {_SECTION}.timeout_seconds must be a number above 0 and at most 60")
    cap = raw.get("max_input_chars", base.max_input_chars)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError(f"config_tuning.json {_SECTION}.max_input_chars must be a positive integer")
    if not isinstance(raw.get("triage_fallback", False), bool):
        raise ValueError(f"config_tuning.json {_SECTION}.triage_fallback must be true or false")
    return ClassifierSettings(
        url=raw.get("url", base.url).strip(), model=raw.get("model", base.model).strip(),
        timeout_seconds=float(timeout), max_input_chars=cap, triage_fallback=raw.get("triage_fallback", False),
        auto_tier=_auto_tier_settings(raw.get("auto_tier", {})),
    )


def _auto_tier_settings(raw: Any) -> AutoTierSettings:
    from src.agents.agent_spec import TIERS  # imported here: agent_spec pulls in the llm package

    where = f"config_tuning.json {_SECTION}.auto_tier"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(raw) - _AUTO_TIER_KNOWN
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    if not isinstance(raw.get("enabled", False), bool):
        raise ValueError(f"{where}.enabled must be true or false")
    confidence = raw.get("min_confidence", AutoTierSettings.min_confidence)
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"{where}.min_confidence must be an integer from 0 to 100")
    mapping = dict(DEFAULT_SIZE_TIERS)
    given = raw.get("tiers", {})
    if not isinstance(given, dict):
        raise ValueError(f"{where}.tiers must be an object of size: tier")
    for size, tier in given.items():
        if size not in SIZE_CRITERIA or tier not in TIERS:
            raise ValueError(f"{where}.tiers maps a size ({', '.join(SIZE_CRITERIA)}) to a tier ({', '.join(TIERS)})")
        mapping[size] = tier
    return AutoTierSettings(enabled=raw.get("enabled", False), min_confidence=confidence, tiers=tuple(mapping.items()))


def reset_cache() -> None:
    """Forget the loaded settings (tests, and a config edit in a long-lived process)."""
    _load_settings.cache_clear()


def api_key() -> str:
    return os.environ.get(KEY_ENV, "").strip()


def available() -> bool:
    """True when a key is set; whether a feature is switched on is `settings()`."""
    return bool(api_key())


@dataclass(frozen=True)
class Choice:
    choice: str
    confidence: int  # 0-100, as the model reports it; not a calibrated probability
    prompt_tokens: int


def _payload(model: str, subject: str, criteria: Mapping[str, str]) -> dict[str, Any]:
    options = " | ".join(criteria)
    lines = "\n".join(f"- {name}: {description}" for name, description in criteria.items())
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a routing classifier. Given input and a set of named "
                    f"options ({options}), pick exactly one option. "
                    "Respond with ONLY a JSON object, no other text: "
                    '{"choice": "<exact option name>", "confidence": <0-100 integer>}'
                ),
            },
            {"role": "user", "content": f"{subject}\n\nOptions:\n{lines}"},
        ],
        "temperature": 0,
    }


def _post(url: str, payload: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise ClassifierError(f"the gateway answered HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ClassifierError(f"the gateway could not be reached: {error}") from error
    except ValueError as error:
        raise ClassifierError("the gateway sent something that is not JSON") from error


def _parse(body: Any, criteria: Mapping[str, str]) -> Choice:
    try:
        content = body["choices"][0]["message"]["content"]
        prompt_tokens = body.get("usage", {}).get("prompt_tokens", 0)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ClassifierError("the gateway's answer has an unexpected shape") from error
    text = str(content).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(text)
        choice = parsed["choice"]
        confidence = int(parsed["confidence"])
    except (ValueError, KeyError, TypeError) as error:
        raise ClassifierError("the answer is not the requested JSON") from error
    if choice not in criteria:
        raise ClassifierError(f"the answer names an option that was not offered: {choice!r}")
    if isinstance(prompt_tokens, bool) or not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        prompt_tokens = 0
    return Choice(choice, max(0, min(100, confidence)), prompt_tokens)


@catalog
def ask_choice(subject: str, criteria: Mapping[str, str], timeout: float | None = None) -> Choice:
    """Which of `criteria` (option -> one-line description) fits `subject` best, and how sure.
    Raises ClassifierError when there is no key, the call fails or the answer is unusable."""
    key = api_key()
    if not key:
        raise ClassifierError(f"{KEY_ENV} is not set")
    if len(criteria) < 2:
        raise ClassifierError("a choice needs at least two options")
    config = settings()
    body = _post(config.url, _payload(config.model, subject, criteria), key, timeout or config.timeout_seconds)
    return _parse(body, criteria)


@catalog
def classify_size(message: str, timeout: float | None = None) -> Choice:
    """How hard `message` looks: one of SIZE_CRITERIA's names, with the classifier's confidence."""
    return ask_choice(message, SIZE_CRITERIA, timeout)
