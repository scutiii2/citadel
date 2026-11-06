"""Bounded, factual traces and phase measurements for deterministic calculations."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter

from src.capabilities.math.contract import Diagnostic, TraceStep


class EvidenceCollector:
    """Record operations when performed; never synthesize a reasoning narrative."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.steps: list[TraceStep] = []
        self.diagnostics: list[Diagnostic] = []
        self.timings = {"parse_ms": 0.0, "solve_ms": 0.0, "verification_ms": 0.0}
        self.completeness = "complete"

    def record(self, action: str, detail: str) -> None:
        if self.enabled and len(self.steps) < 128:
            self.steps.append(TraceStep(action=action, detail=detail[:2048]))

    def diagnose(self, code: str, detail: str, suggestion: str, variables: list[str] | None = None) -> None:
        if len(self.diagnostics) < 32:
            self.diagnostics.append(Diagnostic(code=code, detail=detail, suggestion=suggestion, variables=variables or []))

    @contextmanager
    def measure(self, phase: str):
        started = perf_counter()
        try:
            yield
        finally:
            self.timings[phase] = self.timings.get(phase, 0.0) + (perf_counter() - started) * 1000
