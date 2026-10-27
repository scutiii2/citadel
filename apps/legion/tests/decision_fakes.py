"""Injectable decision gateways for strategy and router contract tests."""
from src.providers.decision.contract import DecisionError, GatewayResult


class Fake:
    def __init__(self, id, local, confidence=None, fail=False, available=True, *, pick=None, tokens=3, model=None):
        self.id, self.local, self.confidence, self.fail = id, local, confidence, fail
        self._available, self.pick, self.tokens, self.model = available, pick, tokens, model or id
        self.asked, self.requests, self.timeouts = [], [], []

    def available(self):
        return self._available

    def ask(self, request, timeout=None):
        self.asked.append(sorted(request.questions))
        self.requests.append(request)
        self.timeouts.append(timeout)
        if isinstance(self.fail, Exception):
            raise self.fail
        if self.fail:
            raise DecisionError(f"{self.id} down")
        answers = {}
        for qid, spec in request.questions.items():
            options = spec["criteria"]
            pick = self.pick.get(qid) if isinstance(self.pick, dict) else self.pick
            picked = pick if pick in options else next(iter(options))
            answers[qid] = {"type": "choice", "choice": picked, "answer_confidence": self.confidence,
                            "uncertain": self.confidence < (0.9 if request.min_confidence is None else request.min_confidence)}
        return GatewayResult(answers, self.tokens, self.model)
