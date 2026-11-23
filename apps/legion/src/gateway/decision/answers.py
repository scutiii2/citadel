"""Native answers (TypeSafe's and Ollama's /v1/systemone) in the shared answer shape, and the `uncertain` rule."""
from __future__ import annotations

import math
from typing import Any

TRACE_KEYS = ("rounds", "voters", "options", "disagreement", "resolved_by", "eliminated")
_EPSILON = 1e-9


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _unit(value: Any) -> float:
    if not _number(value) or not 0 <= value <= 1:
        raise ValueError("invalid probability")
    return float(value)


def _confidence(raw: dict[str, Any]) -> float:
    return _unit(raw["confidence"])


def answer_from(spec: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """One native answer, validated against its question. Raises ValueError on anything unusable."""
    kind = spec["type"]
    out: dict[str, Any] = {"type": kind}
    if kind == "choice":
        choice, probabilities = raw["choice"], raw["probabilities"]
        if choice not in spec["criteria"] or set(probabilities) != set(spec["criteria"]):
            raise ValueError("unknown choice")
        out["choice"] = choice
        out["probabilities"] = {key: _unit(value) for key, value in probabilities.items()}
        out["answer_confidence"] = _confidence(raw)
    elif kind == "score":
        score = raw["score"]
        if not _number(score) or not 0 <= score <= len(spec["criteria"]) - 1:
            raise ValueError("invalid score")
        out["score"] = round(float(score), 4)
        out["legend"] = {str(i): level for i, level in enumerate(spec["criteria"])}
        out["answer_confidence"] = _confidence(raw)
    elif kind == "noul":
        noul = _unit(raw["noul"])
        out["noul"] = noul
        out["answer_confidence"] = max(noul, 1 - noul)  # no confidence for yes/no: the stronger side
    else:
        box = raw["box"]
        sides = {name: _unit(box.get(name)) for name in ("top", "bottom", "left", "right")}
        if sides["top"] >= sides["bottom"] or sides["left"] >= sides["right"]:
            raise ValueError("invalid box")
        out["box"] = sides
        out["answer_confidence"] = None if raw.get("confidence") is None else _confidence(raw)
    return out


def default_threshold(spec: dict[str, Any]) -> float | None:
    """The bars Ollama's d3 uses (Laya English's numbers, not measured for d3): 2 options 0.90, 3 or more 0.75."""
    kind = spec["type"]
    if kind == "box":
        return None
    if kind == "noul":
        return 0.9
    return 0.9 if len(spec["criteria"]) == 2 else 0.75


def mark(answer: dict[str, Any], spec: dict[str, Any], minimum: float | None, default: float | None) -> None:
    """Sets `uncertain`. `minimum` is the caller's min_confidence, `default` the gateway's own bar. A box with no
    confidence is uncertain only when the caller set a minimum, because that bar cannot be checked."""
    confidence = answer["answer_confidence"]
    if confidence is None:
        answer["uncertain"] = minimum is not None
        return
    bar = minimum if minimum is not None else default
    answer["uncertain"] = bar is not None and confidence < bar - _EPSILON


def compact(answer: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in answer.items() if key not in TRACE_KEYS}
