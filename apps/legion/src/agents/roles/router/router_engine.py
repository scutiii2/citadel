"""Router's deterministic preparation and shared triage execution; no delegation."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from src.agents.roles.router.router_contract import DecisionOutcome, RouterPolicy, RouteRequest, RouteResponse, VoterUsage
from src.providers.decision import questions as decision_questions, strategy
from src.providers.decision.contract import DecisionRequest, DecisionError


BATCH_LIMIT = 9        # most options one agent question carries
PRUNE_RATIO = 0.25     # a batch keeps options at least this fraction as likely as its pick
NEAR_TIE_RATIO = 0.8   # a runner-up this close to the winner is reported as an alternative
_AGENT_QUESTION = "Which specialist best fits, or none for the general assistant?"
_NONE_OPTION = "The general assistant should answer; no specialist needed"


def _agent_question(candidates):
    return {"type": "choice", "instructions": _AGENT_QUESTION,
            "criteria": {**{c.id: c.focus or c.label for c in candidates}, "none": _NONE_OPTION}}


def _batches(items, limit=BATCH_LIMIT):
    """Fewest batches of at most `limit`, as equal in size as possible (sizes differ by at most one)."""
    count = -(-len(items) // limit)
    base, extra = divmod(len(items), count)
    out, start = [], 0
    for i in range(count):
        end = start + base + (i < extra)
        out.append(items[start:end])
        start = end
    return out


def _probabilities(answer, options):
    """Per-option probabilities of a choice answer. A gateway that reports none gets the pick's confidence
    and an even share of the rest, which prunes nothing but the pick's own batch-mates."""
    given = answer.get("probabilities")
    if isinstance(given, dict) and set(options) <= set(given):
        return {o: float(given[o]) for o in options}
    pick, confidence = answer.get("choice"), answer.get("answer_confidence", 0)
    rest = [o for o in options if o != pick]
    share = (1 - confidence) / len(rest) if rest else 0.0
    return {o: confidence if o == pick else share for o in options}


class RouterEngine:
    def __init__(self, gateways=None):
        self.gateways = gateways

    @staticmethod
    def _narrow(candidates, ask, pool):
        """Cut a long roster to at most BATCH_LIMIT finalists. Each round splits the candidates into equal
        batches and asks them in parallel. A batch whose pick is `none` drops out whole; otherwise it keeps
        the options not far below its pick. A round that prunes nothing keeps only each batch's pick, so
        rounds always shrink."""
        while len(candidates) > BATCH_LIMIT:
            batches = _batches(candidates)
            answers = list(pool.map(lambda batch: ask({"agent": _agent_question(batch)}).answers.get("agent") or {}, batches))
            kept, picks = [], []
            for batch, answer in zip(batches, answers):
                ids = [c.id for c in batch]
                pick = answer.get("choice")
                if pick not in ids:
                    continue
                odds = _probabilities(answer, [*ids, "none"])
                kept += [c for c in batch if odds[c.id] >= PRUNE_RATIO * odds[pick]]
                picks.append(next(c for c in batch if c.id == pick))
            candidates = picks if len(kept) >= len(candidates) else kept
        return candidates

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
        alternatives = []
        questions = {}
        want_agent = request.choose_agent and policy.choose_agent and bool(request.candidates)
        batching = want_agent and len(request.candidates) > BATCH_LIMIT
        if want_agent and not batching:
            questions["agent"] = _agent_question(request.candidates)
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
            return RouteResponse(agent=agent, size=size, model_tier=tier, alternatives=alternatives,
                                 policy_revision=policy.revision(), usage=list(usage), trace=trace)

        def abstain(reason):
            nonlocal agent, size
            if want_agent:
                agent = DecisionOutcome(reason=reason)
            if "size" in questions:
                size = DecisionOutcome(reason=reason)
            return response()

        if not questions and not batching:
            return response()
        try:
            check()
            if len(request.subject) > 16000:
                return abstain("input_too_long")

            def ask(asked):
                return strategy.run(
                    policy.strategy, DecisionRequest(request.subject, asked, policy.min_confidence, local_only=False),
                    gateways=self.gateways, on_usage=observed, check=check, remote_timeout=policy.remote_timeout_seconds)

            if batching:
                with ThreadPoolExecutor() as pool:
                    size_run = pool.submit(ask, {"size": questions["size"]}) if "size" in questions else None
                    finalists = self._narrow(request.candidates, ask, pool)
                    answers = {}
                    if finalists:
                        questions["agent"] = _agent_question(finalists)
                        answers.update(ask({"agent": questions["agent"]}).answers)
                    else:
                        agent = DecisionOutcome(reason="no_specialist")
                    if size_run:
                        answers.update(size_run.result().answers)
            else:
                answers = ask(questions).answers
            check()
            outcomes = {}
            for key, answer in answers.items():
                choices = questions[key]["criteria"]
                settled = not answer.get("uncertain", True) and not answer.get("unknown") and answer.get("choice") in choices
                outcomes[key] = DecisionOutcome(choice=answer.get("choice") if answer.get("choice") in choices else None,
                    confidence=answer.get("answer_confidence", 0), uncertain=not settled,
                    answered_by=answer.get("answered_by", ""), reason="settled" if settled else "uncertain")
                if key == "agent" and settled and answer["choice"] != "none":
                    odds = _probabilities(answer, list(choices))
                    top = odds[answer["choice"]]
                    alternatives = sorted((o for o in choices if o not in (answer["choice"], "none")
                                           and top > 0 and odds[o] >= NEAR_TIE_RATIO * top), key=lambda o: -odds[o])
            agent, size = outcomes.get("agent", agent), outcomes.get("size", size)
            trace = [{"question": qid, "answered_by": a.get("answered_by")} for qid, a in answers.items()] if policy.trace else None
            return response(trace)
        except InterruptedError:
            return abstain("cancelled")
        except TimeoutError:
            return abstain("timeout")
        except (ValueError, RuntimeError, DecisionError):
            return abstain("unavailable")
