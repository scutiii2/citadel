"""Task-shaped architects that add one rule each: review, writing, operations."""

from __future__ import annotations

from src.agents.roles.architect.task import TaskArchitect
from src.agents.roles.architect.types import NodeResult, Unit, UnitPlan
from src.runtime import tool_filter


class ReviewArchitect(TaskArchitect):
    single_passthrough = False
    guidance = (
        "First the units that produce the answer: one unit, or for a question with several parts one researcher "
        "or specialist unit per part so they run in parallel. Then one reviewer unit that depends on all of them "
        "and checks the answer and its sources for errors and missing steps. If the review would change the "
        "answer, add a last unit by the same specialist that depends on the reviewer and rewrites it. "
    )

    def guidance_for_plan(self) -> str:
        if tool_filter.REVIEW_RESERVED in tool_filter.blocked():
            return "Prepare the answer using the available workers; an independent review follows automatically. "
        return self.guidance

    def assemble_prompt(self, brief: str, plan: UnitPlan, results: dict[str, NodeResult]) -> str:
        return super().assemble_prompt(brief, plan, results).replace(
            "Write the final reply", "Cite the source each claim came from and mark claims only one source supports. "
            "Write the final reply", 1)

    def check_plan(self, units: list[Unit]) -> None:
        if tool_filter.REVIEW_RESERVED in tool_filter.blocked():
            return
        reviews = [unit for unit in units if unit.agent_id == "reviewer"]
        if len(units) < 2 or not reviews:
            raise ValueError("a review plan needs a unit that answers and a reviewer unit that checks it")
        if units[0].agent_id == "reviewer" or not all(unit.depends_on for unit in reviews):
            raise ValueError("the first unit must not be the reviewer, and every reviewer unit must depend on the work it checks")


class WritingArchitect(TaskArchitect):
    single_passthrough = False
    check_figures = False
    guidance = (
        "For a long text: one outline unit with no dependencies, then one unit per section that depends only on "
        "the outline, so sections run in parallel. A short text is one unit. "
    )

    def check_plan(self, units: list[Unit]) -> None:
        if len(units) > 1:
            roots = [unit for unit in units if not unit.depends_on]
            if len(roots) != 1 or any(unit.depends_on != (roots[0].id,) for unit in units if unit is not roots[0]):
                raise ValueError("a long text needs one outline unit and sections that depend only on it")

    def assemble_prompt(self, brief: str, plan: UnitPlan, results: dict[str, NodeResult]) -> str:
        return super().assemble_prompt(brief, plan, results).replace(
            "Write the final reply", "Join the sections in outline order with one consistent tone and no repeats. "
            "Write the final reply", 1)


class OperationsArchitect(TaskArchitect):
    single_passthrough = False
    guidance = (
        "Diagnose before you change anything: read units (effect read) come first. Every unit that changes "
        "something (effect write) must depend on a read unit and must be followed by a read unit that depends on it "
        "and verifies the result. Never put a write before the read that justifies it. "
    )

    def check_plan(self, units: list[Unit]) -> None:
        reads = {unit.id for unit in units if unit.effect == "read"}
        for unit in units:
            if unit.effect != "write":
                continue
            if not reads & set(unit.depends_on):
                raise ValueError(f"write unit {unit.id!r} must depend on a read unit that justifies it")
            if not any(other.effect == "read" and unit.id in other.depends_on for other in units):
                raise ValueError(f"write unit {unit.id!r} needs a later read unit that verifies it")

    def assemble_prompt(self, brief: str, plan: UnitPlan, results: dict[str, NodeResult]) -> str:
        return super().assemble_prompt(brief, plan, results).replace(
            "Write the final reply", "List every change made and how to undo it, and say whether the verifying "
            "read confirmed it. Write the final reply", 1)
