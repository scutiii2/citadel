"""A stand-in for the real Laya engine: tests inject it into LayaClient."""

from __future__ import annotations

import time
from typing import Any


class FakeEngine:
    """Answers every choice question with `pick` (default: the first option)."""

    def __init__(self, pick: str | None = None, confidence: float = 0.9, delay: float = 0.0, usage: dict | None = None) -> None:
        self.pick, self.confidence, self.delay = pick, confidence, delay
        self.usage = usage if usage is not None else {"input_tokens": 10}
        self.calls: list[tuple[str, dict]] = []

    def predict(self, text: str, questions: dict[str, Any], max_len: int = 512) -> dict[str, Any]:
        self.calls.append((text, questions))
        if self.delay:
            time.sleep(self.delay)
        answers = {}
        for qid, spec in questions.items():
            keys = list(spec["criteria"])
            choice = self.pick if self.pick in keys else keys[0]
            probabilities = {key: (self.confidence if key == choice else (1 - self.confidence) / (len(keys) - 1)) for key in keys}
            answers[qid] = {"choice": choice, "probabilities": probabilities, "answer_confidence": self.confidence}
        return {"answers": answers, "usage": self.usage}
