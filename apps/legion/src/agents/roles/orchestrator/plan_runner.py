"""One plan submission session per provider turn, including one repair chance."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from src.agents.agent_spec import ArchitectLimits
from src.agents.roles.architect.executor import DagExecutor, call_worker
from src.agents.roles.architect.types import NodeResult, Plan
from src.agents.roles.orchestrator import catalog, plan, submit_plan
from src.providers.base_provider import OnEvent
from src.runtime import questions


class PlanSession:
    def __init__(self, snapshot: catalog.Catalog) -> None:
        self.catalog = snapshot
        self.failures = 0
        self.closed = False

    async def handle(self, name: str, arguments: Any, depth: int, request_id: str | None,
                     on_event: OnEvent | None) -> tuple[str, bool] | None:
        if name != submit_plan.TOOL_NAME:
            if name == "ask_user" and questions.current().enabled and not self.closed:
                return None
            return f"Tool {name!r} is not offered in this plan-mode round.", False
        if self.closed:
            return "submit_plan is not offered again. Answer directly from the available results.", False
        submitted, error = submit_plan.validate(arguments, self.catalog.architect_ids,
                                                architect_kinds=self.catalog.architect_kinds)
        if submitted is None:
            self.failures += 1
            if self.failures >= 2:
                self.closed = True
                return error + "\nAnswer directly; do not submit another plan.", False
            return error, False
        self.closed = True
        results = await self._execute(submitted, depth, request_id, on_event)
        return json.dumps({"steps": {key: asdict(value) for key, value in results.items()},
                           "instruction": "Write the final reply from these results. Report failures and skipped work accurately."},
                          ensure_ascii=False), True

    async def _execute(self, submitted: Plan, depth: int, request_id: str | None,
                       on_event: OnEvent | None) -> dict[str, NodeResult]:
        checklist = plan.Checklist()
        items = [{"text": step.brief[:300], "status": "pending"} for step in submitted.steps]

        async def update() -> None:
            if plan.current().offered:
                await checklist.handle(plan.TOOL_NAME, {"items": [dict(item) for item in items]}, on_event)

        await update()
        indexes = {step.id: index for index, step in enumerate(submitted.steps)}

        async def run(node, tier, dependencies):
            item = items[indexes[node.id]]
            if not any(row["status"] == "in_progress" for row in items):
                item["status"] = "in_progress"
                await update()
            try:
                return await call_worker(node, tier, dependencies, depth=depth, on_event=on_event)
            finally:
                item["status"] = "done"
                await update()

        results = await DagExecutor(ArchitectLimits(max_retries=0), emit_agent_events=False).run(submitted.steps, run, request_id)
        for step, item in zip(submitted.steps, items):
            result = results[step.id]
            item["status"] = "done"
            if result.status != "done":
                item["text"] = f"{result.status}: {step.brief}"[:300]
        await update()
        return results


async def for_turn() -> PlanSession | None:
    return PlanSession(await catalog.for_turn()) if submit_plan.enabled() else None
