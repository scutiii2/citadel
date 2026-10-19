"""`check_triage_cases --three-way`: the Triage Assistant's flow (src/llm/triage_flow.py, where the rules are
written down) run over loaded checkpoints. The flow itself moved there; this file only loads the two Laya checkpoints
at the window the script asks for and re-exports what the script and its tests use.
"""

from __future__ import annotations

from src.llm.decision import TRIAGE_COUNTS, TRIAGE_VOTERS
from src.llm.laya_provider import LayaQuestions
from src.llm.triage_flow import (  # noqa: F401 - re-exported
    CHECKPOINTS, DEFAULT_THRESHOLDS, ENGLISH, JEV, MAX_NARROWING, TYPED, TriageFlow, final_answer,
)


def parse_threshold(text: str) -> tuple[str, str, float]:
    """`laya-typed:3+=0.6` -> ("laya-typed", "3+", 0.6)."""
    try:
        left, value = text.split("=")
        name, count = left.split(":")
        number = float(value)
    except ValueError as error:
        raise SystemExit(f"--threshold wants MODEL:COUNT=VALUE, for example laya-typed:3+=0.6 (got {text!r})") from error
    if name not in TRIAGE_VOTERS or count not in TRIAGE_COUNTS or not 0 < number <= 1:
        raise SystemExit(f"--threshold {text!r}: MODEL is one of {', '.join(TRIAGE_VOTERS)}; COUNT is 2 or 3+; VALUE is 0-1")
    return name, count, number


class ThreeWayTriage(TriageFlow):
    """TriageFlow that can load its own checkpoints and be reused across requests (one at a time). It always returns
    the full answer: the script's tables and path labels read the trace."""

    def __init__(
        self, locals_: dict[str, LayaQuestions], use_fallback: bool = True,
        thresholds: dict[str, dict[str, float]] | None = None, trace: bool | None = True,
    ) -> None:
        super().__init__(locals_, use_fallback, thresholds, trace)

    @classmethod
    def load(
        cls, max_len: int, use_fallback: bool = True, thresholds: dict[str, dict[str, float]] | None = None,
    ) -> "ThreeWayTriage":
        import laya

        models = {name: LayaQuestions(laya.load(model), window=max_len) for name, model in CHECKPOINTS.items()}
        return cls(models, use_fallback, thresholds)

    def prepare(self) -> None:
        for questions in self.locals.values():
            questions._warm()
