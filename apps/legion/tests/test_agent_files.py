"""Every tracked agent file loads with a role; ids map to the expected roles."""

from src.agents import agent_spec


def test_tracked_agent_files_load_with_roles():
    specs = {s.id: s for s in agent_spec.load_dir(agent_spec.AGENTS_DIR)}
    assert specs["ember"].role == "orchestrator"
    assert specs["router"].role == "router"
    assert all(s.role in agent_spec.ROLES for s in specs.values())
    assert sum(s.role == "orchestrator" for s in specs.values()) >= 1
