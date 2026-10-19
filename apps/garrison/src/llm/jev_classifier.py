"""Decision backend `jev_vercel`: typesafe-ai/jev through Vercel AI Gateway.

OpenAI-style chat completions: a system prompt asks for `{"choice", "confidence"}`
JSON, so the confidence (0-100) is the model's own report, not a probability.
Needs VERCEL_GATEWAY_API_KEY in `.env`. See llm/decision.py for the chain it joins.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from src.llm import decision
from src.llm.decision import Choice, ClassifierError

ID = "jev_vercel"
KEY_ENV = "VERCEL_GATEWAY_API_KEY"


def api_key() -> str:
    return os.environ.get(KEY_ENV, "").strip()


def available() -> bool:
    return bool(api_key())


def _payload(model: str, subject: str, criteria: Mapping[str, str], question: str) -> dict[str, Any]:
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
            {"role": "user", "content": f"{subject}\n\nQuestion: {question}\n\nOptions:\n{lines}"},
        ],
        "temperature": 0,
    }


def _post(url: str, payload: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    return decision.post_json(url, payload, key, timeout, "the gateway")


def _parse(body: Any, criteria: Mapping[str, str], model: str = "") -> Choice:
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
    return Choice(choice, max(0, min(100, confidence)), prompt_tokens, ID, model)


def ask_choice(subject: str, criteria: Mapping[str, str], question: str, timeout: float) -> Choice:
    key = api_key()
    if not key:
        raise ClassifierError(f"{KEY_ENV} is not set")
    config = decision.settings().vercel
    body = _post(config.url, _payload(config.model, subject, criteria, question), key, timeout)
    return _parse(body, criteria, config.model)
