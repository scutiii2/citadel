"""Router's deterministic preparation and shared triage execution; no delegation."""
from __future__ import annotations

import time

from src.agents.roles.router.router_contract import DecisionOutcome, RouterPolicy, RouteRequest, RouteResponse, VoterUsage
from src.providers.decision import questions as decision_questions, strategy
from src.providers.decision.contract import DecisionRequest, DecisionError


class RouterEngine:
    def __init__(self, gateways=None):
        self.gateways = gateways

    def route(self, request: RouteRequest, policy: RouterPolicy, *, cancelled=lambda: False,
              clock=time.monotonic, on_usage=None) -> RouteResponse:
        deadline = clock() + policy.deadline_seconds
        usage = []

        def check():
            if cancelled():
                raise InterruptedError("cancelled")
            remaining = deadline-clock()
            if remaining <= 0:
                raise TimeoutError("timeout")
            return remaining

        def observed(record):
            row = VoterUsage.model_validate(record)
            usage.append(row)
            if on_usage:
                on_usage(row)

        agent, size = DecisionOutcome(), DecisionOutcome()
        questions = {}
        if request.choose_agent and policy.choose_agent and request.candidates:
            if len(request.candidates) > 9:
                agent = DecisionOutcome(reason="too_many_candidates")
            else:
                questions["agent"] = {"type": "choice", "instructions": "Which specialist best fits, or none for the general assistant?",
                    "criteria": {**{c.id: c.focus or c.label for c in request.candidates},
                                 "none": "The general assistant should answer; no specialist needed"}}
        if request.explicit_tier:
            size = DecisionOutcome(reason="explicit_tier")
        elif request.choose_tier and policy.choose_tier:
            questions["size"] = {"type": "choice", "instructions": decision_questions.SIZE_QUESTION,
                                 "criteria": decision_questions.SIZE_CRITERIA}

        def response(trace=None):
            choice = agent.choice if not agent.uncertain else "none"
            target = next((c for c in request.candidates if c.id == choice), request.entry)
            tier = None
            if not size.uncertain and not request.explicit_tier and target and target.tiers:
                tier = policy.size_tiers[size.choice]
                allowed = [t.tier for t in target.tiers]
                levels = ["light", "standard", "heavy", "extreme"]
                tier = min(allowed, key=lambda t: abs(levels.index(t)-levels.index(tier)))
            return RouteResponse(agent=agent, size=size, model_tier=tier,
                                 policy_revision=policy.revision(), usage=list(usage), trace=trace)

        def abstain(reason):
            nonlocal agent, size
            if "agent" in questions:
                agent = DecisionOutcome(reason=reason)
            if "size" in questions:
                size = DecisionOutcome(reason=reason)
            return response()

        if not questions:
            return response()
        try:
            check()
            if len(request.subject) > 16000:
                return abstain("input_too_long")
            result = strategy.run(
                policy.strategy,
                DecisionRequest(request.subject, questions, policy.min_confidence, local_only=False),
                gateways=self.gateways, on_usage=observed, check=check, remote_timeout=policy.remote_timeout_seconds)
            check()
            answers = result.answers
            outcomes = {}
            for key, answer in answers.items():
                choices = questions[key]["criteria"]
                settled = not answer.get("uncertain", True) and not answer.get("unknown") and answer.get("choice") in choices
                outcomes[key] = DecisionOutcome(choice=answer.get("choice") if answer.get("choice") in choices else None,
                    confidence=answer.get("answer_confidence", 0), uncertain=not settled,
                    answered_by=answer.get("answered_by", ""), reason="settled" if settled else "uncertain")
            agent, size = outcomes.get("agent", agent), outcomes.get("size", size)
            trace = [{"question": qid, "answered_by": a.get("answered_by")} for qid, a in answers.items()] if policy.trace else None
            return response(trace)
        except InterruptedError:
            return abstain("cancelled")
        except TimeoutError:
            return abstain("timeout")
        except (ValueError, RuntimeError, DecisionError):
            return abstain("unavailable")
