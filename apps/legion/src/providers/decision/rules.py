"""Which model lists a decision agent may save: untrusted gateways first, then at least one trusted one."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from src.runtime import confidentiality


def order_problem(agent_id: str, names: Sequence[str], is_trusted: Callable[[str], bool]) -> str | None:
    """What is wrong with the list, or None."""
    trusted = [is_trusted(name) for name in names]
    if agent_id == confidentiality.AGENT_ID and not all(trusted):
        return "the Confidentiality Checker takes trusted models only"
    if not any(trusted):
        return "a decision agent needs at least one trusted model"
    if trusted != sorted(trusted):  # False sorts before True
        return "list untrusted models first and trusted models last"
    return None
