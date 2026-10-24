"""Router's deterministic preparation and shared triage execution; no delegation."""
from __future__ import annotations

import json
import time
from dataclasses import replace

from src.agents.router_contract import DecisionOutcome, RouterPolicy, RouteRequest, RouteResponse, VoterUsage
from src.llm import decision
from src.llm.triage_flow import TriageFlow


class RouterEngine:
    def __init__(self, service=None):
        self.service = service  # the LAYAAgent that TriageFlow asks; None means the process-wide one

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
            questions["size"] = {"type": "choice", "instructions": decision.SIZE_QUESTION,
                                 "criteria": decision.SIZE_CRITERIA}

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
        if len(request.subject) > 16000:
            return abstain("input_too_long")
        base = decision.settings()
        config = replace(base, triage_fallback=policy.fallback, triage_thresholds=policy.thresholds,
                         triage_prune_ratio=policy.prune_ratio, triage_pair_ratio=policy.pair_ratio,
                         triage_enabled={v: {kind: enabled for kind in decision.TRIAGE_TYPES}
                                         for v, enabled in (("laya-english", policy.english and len(request.subject) <= 4000),
                                                            ("laya-typed", policy.typed and len(request.subject) <= 4000),
                                                            ("jev", policy.fallback))},
                         triage_order=decision.DEFAULT_TRIAGE_ORDER, max_input_chars=16000,
                         timeout_seconds=policy.remote_timeout_seconds)
        try:
            check()
            if len(request.subject) > 4000 and not (policy.fallback and decision.available("triage", ("laya",))):
                return abstain("input_too_long")
            flow = TriageFlow(trace=True, service=self.service, settings_snapshot=config, check=check,
                              on_usage=observed, partial_results=True)
            answers = json.loads(flow.answer(json.dumps({"text": request.subject, "questions": questions})).response)["answers"]
            check()
            outcomes = {}
            for key, answer in answers.items():
                choices = questions[key]["criteria"]
                settled = not answer.get("uncertain", True) and not answer.get("unknown") and answer.get("choice") in choices
                outcomes[key] = DecisionOutcome(choice=answer.get("choice") if answer.get("choice") in choices else None,
                    confidence=answer.get("answer_confidence", 0), uncertain=not settled,
                    answered_by=answer.get("answered_by", ""), reason="settled" if settled else "uncertain")
            agent, size = outcomes.get("agent", agent), outcomes.get("size", size)
            trace = [{"question": qid, "rounds": a.get("rounds", [])} for qid, a in answers.items()] if policy.trace else None
            return response(trace)
        except InterruptedError:
            return abstain("cancelled")
        except TimeoutError:
            return abstain("timeout")
        except (ValueError, RuntimeError, decision.ClassifierError):
            return abstain("unavailable")
