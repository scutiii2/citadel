"""Router contract smoke cases, or an explicit live classifier comparison.

Offline is the default and uses synthetic predictions: it measures plumbing, not
model accuracy. --live uses the Laya service (LAYA_SERVICE_URL) and environment credentials;
it never dispatches specialist work. Run live only in a prepared deployment.
"""
from __future__ import annotations

import argparse
import json
import time

from src.agents.roles.router.router_contract import RouterPolicy, RouteCandidate, RouteRequest, RouteTier
from src.agents.roles.router.router_engine import RouterEngine
from src.providers.decision import strategy, questions
from src.providers.decision.contract import DecisionError, GatewayResult

CASES = [
    ("general", "What is a prime number?", "none", "tiny"),
    ("server", "List the status of my managed servers", "ops", "tiny"),
    ("research", "Research the available approaches and write a detailed comparison", "researcher", "large"),
    ("complex", "Plan a risky database migration with rollback and failure recovery", "ops", "hardest"),
    ("followup", "and that one?", None, None),
    ("mixed", "Research alternatives, then deploy and monitor the replacement", None, "large"),
    ("attachment", "Inspect the attached table [table_id: example]", "researcher", "everyday"),
    ("long", "x" * 16001, None, None),
]


class FixtureGateway:
    """Synthetic local gateway for contract checks, not model evaluation."""
    id = "laya"
    local = True

    def __init__(self, agent, size):
        self.expected = {"agent": agent, "size": size}

    def available(self):
        return True

    def ask(self, request, timeout=None):
        answers = {}
        for qid, spec in request.questions.items():
            choices = list(spec["criteria"])
            expected = self.expected[qid]
            chosen = expected if expected in choices else choices[0]
            confidence = .99 if expected is not None else .1
            answers[qid] = {"type": "choice", "choice": chosen, "answer_confidence": confidence,
                "uncertain": confidence < request.min_confidence,
                "probabilities": {c: .99 if c == chosen else .01/(len(choices)-1) for c in choices}}
        return GatewayResult(answers, tokens=1, model="fixture")


def evaluate(*, live=False):
    tiers = [RouteTier(tier=t) for t in ("light", "standard", "heavy")]
    candidates = [RouteCandidate(id="ops", label="Operations", focus="Server status, deployments and database operations", tiers=tiers),
                  RouteCandidate(id="researcher", label="Researcher", focus="Research, comparisons and tabular analysis", tiers=tiers)]
    rows = []
    for name, subject, expected_agent, expected_size in CASES:
        request = RouteRequest(subject=subject, candidates=candidates, request_id=f"evaluation-{name}",
                               entry=RouteCandidate(id="ember", label="Ember", tiers=tiers))
        if live:
            engine, policy = RouterEngine(), RouterPolicy()
        else:
            engine = RouterEngine(gateways={"laya": FixtureGateway(expected_agent, expected_size)})
            policy = RouterPolicy(strategy="laya-only")
        started = time.monotonic()
        result = engine.route(request, policy)
        actual_agent = None if result.agent.uncertain else result.agent.choice
        actual_size = None if result.size.uncertain else result.size.choice
        row = {"case": name, "agent": actual_agent, "size": actual_size, "tier": result.model_tier,
               "abstained": result.agent.uncertain, "elapsed_ms": round((time.monotonic()-started)*1000),
               "remote_calls": sum(r.provider_id != "laya" for r in result.usage),
               "contract_ok": actual_agent == expected_agent and actual_size == expected_size}
        if live:
            direct = {}
            direct_started = time.monotonic()
            try:
                # Match the Router input limits; this is a comparison, not the retired runtime path.
                if len(subject) > 16000:
                    raise ValueError("input_too_long")
                choices = {c.id: c.focus for c in candidates} | {"none": "The general assistant should answer"}
                agent = strategy.ask_choice(subject, choices, "Which specialist fits?", strategy="jev-only", min_confidence=60, timeout=3)
                size = strategy.ask_choice(subject, questions.SIZE_CRITERIA, questions.SIZE_QUESTION, strategy="jev-only", min_confidence=60, timeout=3)
                direct = {"agent": agent.choice if agent.confidence >= 60 else None,
                          "size": size.choice if size.confidence >= 60 else None, "remote_calls": 2}
            except (DecisionError, ValueError):
                direct = {"agent": None, "size": None, "unavailable": True}
            row["direct_jev"] = {**direct, "elapsed_ms": round((time.monotonic()-direct_started)*1000)}
        rows.append(row)
    return {"mode": "live_comparison" if live else "offline_contract_fixtures", "cases": rows,
            "remote_calls": sum(r["remote_calls"] for r in rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true")
    modes.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(live=args.live)
    print(json.dumps(result, indent=2))
    return 0 if args.live or all(r["contract_ok"] for r in result["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
