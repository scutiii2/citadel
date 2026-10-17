"""Decision backend `jev`: TypeSafe's own Jev API (POST /v1/systemone).

Typed questions with real probabilities. One `choice` question is sent per call; its
`confidence` (0-1, how peaked the distribution is) becomes the 0-100 number the
other backends use. Needs TYPESAFE_API_KEY in `.env`. See llm/decision.py for the chain it joins.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from src.llm import decision
from src.llm.decision import Choice, ClassifierError

ID = "jev"
KEY_ENV = "TYPESAFE_API_KEY"
_QUESTION_ID = "answer"


def api_key() -> str:
    return os.environ.get(KEY_ENV, "").strip()


def available() -> bool:
    return bool(api_key())


def _payload(model: str, subject: str, criteria: Mapping[str, str], question: str) -> dict[str, Any]:
    return {
        "state": subject,
        "model": model,
        "questions": {_QUESTION_ID: {"type": "choice", "instructions": question, "criteria": dict(criteria)}},
    }


def _post(url: str, payload: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    return decision.post_json(url, payload, key, timeout, "TypeSafe")


def _parse(body: Any, criteria: Mapping[str, str]) -> Choice:
    try:
        answer = body["answers"][_QUESTION_ID]
        choice = answer["choice"]
        confidence = answer["confidence"]
        model = str(body.get("model", ""))
        tokens = body.get("usage", {}).get("input_tokens", 0)
    except (KeyError, TypeError, AttributeError) as error:
        raise ClassifierError("TypeSafe's answer has an unexpected shape") from error
    if choice not in criteria:
        raise ClassifierError(f"the answer names an option that was not offered: {choice!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ClassifierError("TypeSafe's answer has no usable confidence")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        tokens = 0
    return Choice(choice, round(confidence * 100), tokens, ID, model)


def ask_choice(subject: str, criteria: Mapping[str, str], question: str, timeout: float) -> Choice:
    key = api_key()
    if not key:
        raise ClassifierError(f"{KEY_ENV} is not set")
    config = decision.settings().typesafe
    body = _post(config.url, _payload(config.model, subject, criteria, question), key, timeout)
    return _parse(body, criteria)
