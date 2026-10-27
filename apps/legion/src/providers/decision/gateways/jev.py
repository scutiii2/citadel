"""Decision gateway `jev`: TypeSafe's Jev API (POST /v1/systemone), a cloud call.

Jev takes one `choice` question per call, so score levels and noul true/false are asked as a choice over
those options and mapped back to the Laya answer shape the rest of Legion reads."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from src.providers import llm_config
from src.providers.decision.contract import DecisionError, DecisionRequest, GatewayResult

ID = "jev"
KEY_ENV = "TYPESAFE_API_KEY"
_QUESTION_ID = "answer"
_NOUL_DEFAULTS = {"false": "No: the statement is false.", "true": "Yes: the statement is true."}
_DEFAULT_TIMEOUT = 3.0
# Jev reports one confidence and has no thresholds of its own, so a request without a minimum uses this one.
DEFAULT_THRESHOLD = 0.9

Post = Callable[[str, dict[str, Any], str, float], dict[str, Any]]


def _post_json(url: str, payload: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise DecisionError(f"TypeSafe answered HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise DecisionError(f"TypeSafe could not be reached: {error}") from error
    except ValueError as error:
        raise DecisionError("TypeSafe sent something that is not JSON") from error


def _options(spec: Mapping[str, Any]) -> dict[str, str]:
    """The question's options as Jev names them: choices as given, score levels "0", "1", ... and noul "false"/"true"."""
    if spec["type"] == "choice":
        return dict(spec["criteria"])
    if spec["type"] == "score":
        return {str(i): f"level {i}: {level}" for i, level in enumerate(spec["criteria"])}
    return dict(spec.get("criteria") or _NOUL_DEFAULTS)


def _question_text(spec: Mapping[str, Any]) -> str:
    text = spec["instructions"]
    return text + " Pick the level that fits best; level 0 is the lowest." if spec["type"] == "score" else text


def _parse(body: Any, options: Mapping[str, str]) -> tuple[str, float, dict[str, float] | None, int, str]:
    try:
        answer = body["answers"][_QUESTION_ID]
        choice, confidence = answer["choice"], answer["confidence"]
        model = str(body.get("model", ""))
        tokens = body.get("usage", {}).get("input_tokens", 0)
    except (KeyError, TypeError, AttributeError) as error:
        raise DecisionError("TypeSafe's answer has an unexpected shape") from error
    if choice not in options:
        raise DecisionError(f"the answer names an option that was not offered: {choice!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise DecisionError("TypeSafe's answer has no usable confidence")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        tokens = 0
    raw = answer.get("probabilities")
    real = None
    if isinstance(raw, dict) and set(raw) == set(options) and all(
            not isinstance(v, bool) and isinstance(v, (int, float)) and 0 <= v <= 1 for v in raw.values()):
        real = {name: float(raw[name]) for name in options}
    return choice, float(confidence), real, tokens, model


def _answer(spec: Mapping[str, Any], choice: str, confidence: float, real: dict[str, float] | None,
            min_confidence: float) -> dict[str, Any]:
    """Jev's pick in the shape of a Laya answer. A reported distribution is kept; otherwise the other options share what is left."""
    out: dict[str, Any] = {"type": spec["type"]}
    if spec["type"] == "choice":
        others = [name for name in spec["criteria"] if name != choice]
        share = round((1 - confidence) / len(others), 4) if others else 0.0
        out["choice"] = choice
        out["probabilities"] = (
            {name: round(real[name], 4) for name in spec["criteria"]} if real
            else {name: (confidence if name == choice else share) for name in spec["criteria"]}
        )
    elif spec["type"] == "score":
        out["score"] = float(choice)
        out["legend"] = {str(i): level for i, level in enumerate(spec["criteria"])}
    else:
        out["noul"] = confidence if choice == "true" else round(1 - confidence, 4)
    out["answer_confidence"] = confidence
    out["uncertain"] = confidence < min_confidence
    return out


class JevGateway:
    id = ID
    local = False

    def __init__(self, post: Post | None = None) -> None:
        self._post = post or _post_json

    def _block(self) -> dict[str, Any] | None:
        try:
            block = llm_config.gateway("decision", ID)
        except (KeyError, ValueError):
            return None
        return block if str(block.get("api_key", "")).strip() else None

    def available(self) -> bool:
        return bool(os.environ.get(KEY_ENV, "").strip()) and self._block() is not None

    def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        block = self._block()
        key = os.environ.get(KEY_ENV, "").strip()
        if not key or block is None:
            raise DecisionError(f"{KEY_ENV} is not set")
        answers: dict[str, dict[str, Any]] = {}
        tokens, model = 0, str(block.get("model", ""))
        for qid, spec in request.questions.items():
            options = _options(spec)
            payload = {"state": request.text, "model": block["model"],
                       "questions": {_QUESTION_ID: {"type": "choice", "instructions": _question_text(spec),
                                                    "criteria": options}}}
            body = self._post(block["url"], payload, key, timeout or _DEFAULT_TIMEOUT)
            choice, confidence, real, used, reported = _parse(body, options)
            tokens += used
            model = reported or model
            answers[qid] = _answer(spec, choice, confidence, real,
                                   DEFAULT_THRESHOLD if request.min_confidence is None else request.min_confidence)
        return GatewayResult(answers, tokens, model)
