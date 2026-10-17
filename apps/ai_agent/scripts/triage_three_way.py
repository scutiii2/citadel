"""`check_triage_cases --three-way`: the Triage Assistant's sequential flow (src/llm/triage_flow.py, where the rules are
written down) run over loaded checkpoints. The flow itself moved there; this file only loads the two Laya checkpoints
at the window the script asks for and re-exports what the script and its tests use.
"""

from __future__ import annotations

from src.llm.laya_provider import LayaQuestions
from src.llm.triage_flow import (  # noqa: F401 - re-exported
    CHECKPOINTS, DEFAULT_THRESHOLDS, ENGLISH, JEV, MAX_NARROWING, TYPED, TriageFlow, final_answer, parse_threshold,
)


class ThreeWayTriage(TriageFlow):
    """TriageFlow that can load its own checkpoints and be reused across requests (one at a time)."""

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
