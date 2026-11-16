# Plan 10.2: Legion client in Stronghold

Step 10.2 of [Plan 10](2026-11-16-plan-10-turn-engine.md). Executed 2026-11-16 on `refactor/turns-10-2`.

## Finding

Stronghold already held everything this step planned to copy: `src/agents/gateway.py` (`AgentGateway`, `McpAgentGateway`, `Caller`, `ask` with events, `cancel`, `decide`, `answer_question`, `interpret`, `probe_extension`), `directory.py`, `mcp_session.py`, and the settings `AGENTS_REGISTRY_PATH` / `AGENTS_REGISTRY_URL` plus the internal token and the compose wiring (`agent_data` volume). The only difference from Portcullis's copy is that Stronghold's gateway has no traffic recorder.

## Done

- `apps/stronghold/tests/test_agent_gateway.py`: the Portcullis gateway tests ported (31), run against a real in-process MCP agent: event streaming, identity headers, approval options, switched-off tools, ask-user, plan toggles, exact context, decide, cancel, unreachable agent.
- `docker-compose.yml`: comment that Stronghold must run one replica (turn state lives in memory).

## Not done / left for later steps

- No traffic recorder in Stronghold's gateway (Portcullis keeps its own until 10.6).
- Portcullis's `agent_gateway.py` and its test stay until 10.6, because Portcullis turns still use them.

## Results

Stronghold 636 tests pass. Nothing run against a live Legion.
