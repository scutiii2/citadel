"""Typed skill operations; skill_store owns storage, identity_context the owner.

There is deliberately no approve or retire here: only the user's side (ember_api) may activate a skill.
"""
from src.capabilities.skills.contract import MarkResult, ProposeResult, SearchResult
from src.config import settings
from src.services import identity_context, skill_store, untrusted
from src.services.internal_token import is_exposed_without_token


def _owner() -> str:
    """The caller's uid, after checking that the identity can be trusted at all."""
    if is_exposed_without_token(settings.host, settings.internal_api_token):
        # Without the token any machine that can reach the port could claim any uid.
        raise skill_store.SkillStoreError(
            f"Skills are disabled: this server listens on {settings.host!r} without INTERNAL_API_TOKEN, "
            "so anyone on the network could read saved skills. Set INTERNAL_API_TOKEN, or bind to 127.0.0.1."
        )
    return identity_context.current_uid()


def propose(title: str, when_to_use: str, steps: str, tools: str = "") -> ProposeResult:
    outcome = skill_store.propose(settings.skills_db_path, _owner(), title, when_to_use, steps, tools)
    if outcome.duplicate:
        return ProposeResult(id=outcome.id, message=f"A skill with that title already exists as {outcome.id}; nothing changed.")
    return ProposeResult(id=outcome.id, message=f"Proposed as skill {outcome.id}. It stays unused until the user approves it.")


def search(query: str = "") -> SearchResult:
    skills = skill_store.search(settings.skills_db_path, _owner(), query)
    if not skills:
        return SearchResult(count=0, message="No approved skills match.")
    blocks = [
        f"[{s.id}] {s.title} (worked {s.successes}x, failed {s.failures}x)\n"
        f"When to use: {s.when_to_use}\nSteps: {s.steps}" + (f"\nTools: {s.tools}" if s.tools else "")
        for s in skills
    ]
    # Skill text was written by a model earlier: treat it as data, not instructions.
    body = untrusted.fence("\n\n".join(blocks), source="your approved skills")
    return SearchResult(count=len(skills), message=f"{len(skills)} approved skill(s):\n{body}")


def mark(skill_id: int, outcome: str) -> MarkResult:
    skill = skill_store.mark(settings.skills_db_path, _owner(), skill_id, outcome)
    if skill is None:
        return MarkResult(recorded=False, message=f"No approved skill {skill_id} found.")
    return MarkResult(recorded=True, message=f"Recorded a {outcome} for skill {skill_id} ({skill.successes} worked, {skill.failures} failed).")
