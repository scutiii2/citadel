"""`check_triage_cases --three-way`: the Triage Assistant's flow (src/llm/triage_flow.py, where the rules are
written down) run against the Laya service. The flow itself lives there; this file only sets the window the script asks for
and re-exports what the script and its tests use.
"""

from __future__ import annotations

from src.llm.decision import TRIAGE_COUNTS, TRIAGE_VOTERS
from dataclasses import replace

from src.llm import decision, laya_agent, laya_provider
from src.llm.triage_flow import (
    CHECKPOINTS, DEFAULT_THRESHOLDS, ENGLISH, JEV, TYPED, TriageFlow,
)

__all__ = [
    "CHECKPOINTS", "DEFAULT_THRESHOLDS", "ENGLISH", "JEV", "TYPED", "TriageFlow",
]


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
    """TriageFlow for the script: one window for every request, reusable across requests (one at a time). It always
    returns the full answer: the script's tables and path labels read the trace."""

    @classmethod
    def load(
        cls, max_len: int, use_fallback: bool = True, thresholds: dict[str, dict[str, float]] | None = None,
    ) -> "ThreeWayTriage":
        config = replace(decision.settings(), triage_window=max_len)
        return cls(use_fallback, thresholds, True, settings_snapshot=config)

    def prepare(self) -> None:
        laya_provider.prepare()
        if not laya_agent.agent().health():
            raise SystemExit("The Laya service does not answer: start it and set LAYA_SERVICE_URL")
