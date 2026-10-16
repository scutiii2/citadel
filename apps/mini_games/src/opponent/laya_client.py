"""Local Laya wrapper: ask one typed `choice` question about a short text.

A copy of the contract in ai_agent's laya_provider.py (projects never import
each other). Lazy model load under a lock, inference in a worker thread, and
a timeout so a slow model never stalls a game turn. Laya reads text only; it
generates no text and is never trusted without its own confidence flag.
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import threading
from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL = "convaiinnovations/laya"
CONTEXT_WINDOW = 512
MAX_TEXT_CHARS = 4000
MIN_OPTIONS, MAX_OPTIONS = 2, 10
QUESTION_ID = "move"


class LayaError(RuntimeError):
    """Laya failed, timed out, or returned something unusable."""


class LayaUnavailable(LayaError):
    """The optional `laya` package is not installed."""


@dataclass(frozen=True)
class LayaChoice:
    key: str
    confidence: float
    uncertain: bool


def _unit(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("invalid probability")
    return float(value)


class LayaClient:
    """Engine injection (`engine=`) lets tests run without the real model."""

    def __init__(self, engine: Any = None, timeout: float = 5.0) -> None:
        self._engine = engine
        self._timeout = timeout
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return self._engine is not None or importlib.util.find_spec("laya") is not None

    def _load(self) -> Any:
        # Called only while holding _lock, including during inference.
        if self._engine is None:
            try:
                import laya
            except ImportError as error:
                raise LayaUnavailable('Laya needs the optional dependency: pip install -e ".[laya]"') from error
            self._engine = laya.load(DEFAULT_MODEL)
        return self._engine

    def prepare(self) -> None:
        """Warm the model so the first game turn is not slow."""
        with self._lock:
            self._load()

    def _choose_sync(self, text: str, instructions: str, options: dict[str, str], min_confidence: float) -> LayaChoice:
        if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise LayaError(f"Laya needs {MIN_OPTIONS} to {MAX_OPTIONS} options, got {len(options)}")
        if not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise LayaError(f"text must be 1 to {MAX_TEXT_CHARS} characters")
        questions = {QUESTION_ID: {"type": "choice", "instructions": instructions, "criteria": options}}
        with self._lock:
            prediction = self._load().predict(text, questions, max_len=CONTEXT_WINDOW)
        try:
            usage = prediction.get("usage", {})
            if usage.get("truncated") or usage.get("state_tokens_dropped", 0):
                raise LayaError("Laya could not read the complete input")
            raw = prediction["answers"][QUESTION_ID]
            key = raw["choice"]
            probabilities = raw["probabilities"]
            if key not in options or set(probabilities) != set(options):
                raise ValueError("unknown choice")
            for value in probabilities.values():
                _unit(value)
            confidence = _unit(raw["answer_confidence"])
        except LayaError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise LayaError("Laya returned an invalid result") from error
        return LayaChoice(key, confidence, confidence < min_confidence)

    async def choose(self, text: str, instructions: str, options: dict[str, str], min_confidence: float = 0.7) -> LayaChoice:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._choose_sync, text, instructions, options, min_confidence), self._timeout
            )
        except asyncio.TimeoutError as error:
            raise LayaError(f"Laya timed out after {self._timeout}s") from error
