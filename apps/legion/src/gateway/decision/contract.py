"""One request shape and one answer container for every gateway, and the single definition of a valid request."""
from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import dataclass, field
from typing import Any

from src.gateway.decision.errors import GatewayError

QUESTION_TYPES = ("choice", "score", "noul", "box")
MAX_QUESTIONS = 8
MIN_OPTIONS, MAX_OPTIONS = 2, 10
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_PLACEHOLDER_BYTES = 1024
IMAGE_FORMATS = ("png", "jpg", "jpeg")
_REQUEST_KEYS = {"gateway", "text", "questions", "assets", "min_confidence", "trace", "stream"}
_NOUL_KEYS = {"false", "true"}


@dataclass(frozen=True)
class DecisionRequest:
    gateway: str
    text: str
    questions: dict[str, dict[str, Any]]
    assets: dict[str, dict[str, Any]] = field(default_factory=dict)
    min_confidence: float | None = None
    trace: bool = False
    stream: bool = False


@dataclass(frozen=True)
class GatewayResult:
    answers: dict[str, dict[str, Any]]
    tokens: int = 0
    model: str = ""


def _fail(message: str) -> GatewayError:
    return GatewayError(422, "invalid_request", f"Invalid decision request: {message}")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _check_question(qid: Any, spec: Any) -> None:
    where = f"question {qid!r}"
    if not _is_text(qid):
        raise _fail("question ids must be non-empty strings")
    if not isinstance(spec, dict):
        raise _fail(f"{where} must be an object")
    unknown = set(spec) - {"type", "instructions", "criteria"}
    if unknown:
        raise _fail(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    kind, criteria = spec.get("type"), spec.get("criteria")
    if kind not in QUESTION_TYPES:
        raise _fail(f"{where} type must be choice, score, noul or box")
    if not _is_text(spec.get("instructions")):
        raise _fail(f"{where} needs non-empty instructions")
    if kind == "choice":
        ok = (isinstance(criteria, dict) and MIN_OPTIONS <= len(criteria) <= MAX_OPTIONS
              and all(_is_text(k) and _is_text(v) for k, v in criteria.items()))
        rule = f"an object of {MIN_OPTIONS} to {MAX_OPTIONS} option: description strings"
    elif kind == "score":
        ok = (isinstance(criteria, list) and MIN_OPTIONS <= len(criteria) <= MAX_OPTIONS
              and all(_is_text(v) for v in criteria))
        rule = f"a list of {MIN_OPTIONS} to {MAX_OPTIONS} level description strings, lowest first"
    elif kind == "noul":
        ok = criteria is None or (isinstance(criteria, dict) and set(criteria) == _NOUL_KEYS
                                  and all(_is_text(v) for v in criteria.values()))
        rule = 'omitted, or an object with exactly the keys "false" and "true"'
    else:
        ok, rule = criteria is None, "omitted (a box question takes only type and instructions)"
    if not ok:
        raise _fail(f"{where} ({kind}) criteria must be {rule}")


def parse_questions(questions: Any) -> None:
    """Raises GatewayError(422) naming the first thing wrong with the questions."""
    if not isinstance(questions, dict) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise _fail(f"questions must be an object with 1 to {MAX_QUESTIONS} entries")
    for qid, spec in questions.items():
        _check_question(qid, spec)


def _check_assets(assets: Any, text: str, questions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(assets, dict) or not assets:
        raise _fail("assets must be a non-empty object of placeholder: image")
    haystack = text + json.dumps(questions, ensure_ascii=False)
    for key, asset in assets.items():
        if not _is_text(key) or len(key.encode("utf-8")) > MAX_PLACEHOLDER_BYTES:
            raise _fail("an asset placeholder must be a non-empty string of at most 1024 bytes")
        if not isinstance(asset, dict):
            raise _fail(f"asset {key!r} must be an object")
        unknown = set(asset) - {"type", "format", "data_base64"}
        if unknown:
            raise _fail(f"asset {key!r} has unknown field(s): {', '.join(sorted(unknown))}")
        if asset.get("type") != "image":
            raise _fail(f"asset {key!r} type must be image")
        if asset.get("format") not in IMAGE_FORMATS:
            raise _fail(f"asset {key!r} format must be png, jpg or jpeg")
        data = asset.get("data_base64")
        if not isinstance(data, str) or not data:
            raise _fail(f"asset {key!r} needs data_base64")
        try:
            size = len(base64.b64decode(data, validate=True))
        except (binascii.Error, ValueError):
            raise _fail(f"asset {key!r} data_base64 is not valid base64") from None
        if size > MAX_IMAGE_BYTES:
            raise _fail(f"asset {key!r} is larger than 16 MiB")
        if key not in haystack:
            raise _fail(f"asset {key!r} is not used in the text or any question")
    return assets


def parse_request(data: Any, max_chars: int, require_gateway: bool = True) -> DecisionRequest:
    if not isinstance(data, dict):
        raise _fail("the request must be a JSON object")
    unknown = set(data) - _REQUEST_KEYS
    if unknown:
        raise _fail(f"unknown field(s): {', '.join(sorted(unknown))}")
    gateway = data.get("gateway", "")
    if require_gateway and not _is_text(gateway):
        raise _fail("gateway must be the id of a configured gateway")
    if not isinstance(gateway, str):
        raise _fail("gateway must be text")
    text = data.get("text")
    if not _is_text(text):
        raise _fail("text must be a non-empty string")
    if len(text) > max_chars:
        raise _fail(f"text must be at most {max_chars} characters")
    questions = data.get("questions")
    parse_questions(questions)
    minimum = data.get("min_confidence")
    if minimum is not None and (not _is_number(minimum) or not 0 < minimum <= 1):
        raise _fail("min_confidence must be a number above 0 and at most 1")
    flags = {}
    for name in ("trace", "stream"):
        flags[name] = data.get(name, False)
        if not isinstance(flags[name], bool):
            raise _fail(f"{name} must be true or false")
    assets: dict[str, dict[str, Any]] = {}
    if "assets" in data:
        assets = _check_assets(data["assets"], text, questions)
    if any(spec["type"] == "box" for spec in questions.values()) and not assets:
        raise _fail("a box question needs at least one image in assets")
    return DecisionRequest(gateway.strip(), text, questions, assets, None if minimum is None else float(minimum),
                           flags["trace"], flags["stream"])


def assets_for(text: str, spec: dict[str, Any], assets: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The assets one upstream call must carry: those whose placeholder appears in the text or in this question."""
    haystack = text + json.dumps(spec, ensure_ascii=False)
    return {key: asset for key, asset in assets.items() if key in haystack}
