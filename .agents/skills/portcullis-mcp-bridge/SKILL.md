---
name: portcullis-mcp-bridge
description: Use when the browser, ember or a Portcullis route must reach Armory, Legion or Stronghold - the MCP proxy and its policies, pass-through routes to Stronghold (chats, turns, brain, skills, tickets, usage, attachments), caller identity headers, server-side tool calls, or agent discovery.
---

# Reaching Armory, Legion and Stronghold from Portcullis

Backend checklist: `portcullis-feature-scaffold`. Tool side: `armory-capability-scaffold`. Agent side: `legion-agent-scaffold`.

The browser never gets a service URL, token or identity header. Everything goes through Portcullis, which authenticates the account, checks the permission, then forwards with signed service and requester assertions (`src/citadel_auth`, `services/service_auth.py`).

## Pick the path

| Need | Path |
|---|---|
| Chats, turns, brain, skills, tickets, usage, attachments, tool services, triage | **Stronghold** owns the logic. Add a thin route that calls `services/stronghold_forwarder.py` and passes Stronghold's answer through. Stronghold answers below 500 go back unchanged; unreachable or 5xx becomes `502`/`503`. Logic does not belong in Portcullis |
| Browser lists or calls an Armory tool or resource | MCP proxy, `routes/mcp.py` with `SERVER_POLICY` (needs `tools.execute`) or `SERVER_VIEW_POLICY` (list and read only, `tools.view`) from `services/mcp_policy.py`. Client: `api/McpServerClient.ts` in ember |
| Armory plain HTTP routes (`/commands`, `/capabilities`) | `services/mcp_server_info.py` + `routes/server_info.py` |
| Portcullis itself needs a tool result (for example command option metadata) | `services/server_tools.py` (`ServerTools` protocol, `McpServerTools`, `FakeServerTools` in tests), behind its own permission, never the browser proxy |
| Ask the Legion entry agent from outside | `services/legion_ask.py` and the outside-client routes (`routes/outside.py`) |
| Which agents exist | `GET /api/agent` (`routes/mcp.py`, `services/agent_directory.py`) reads Legion's registry |

## Rules

- `AGENT_POLICY` allows only `status` on agents. Never add `ask` there: the browser would bypass Stronghold's turn engine and the usage limits.
- Every new MCP call from Portcullis sends the identity headers (`identity_headers` in `services/service_auth.py`). Armory and Legion reject `/mcp` without a signed identity.
- An upstream that is down must not stop Portcullis starting; only that feature fails.
- Log ids and field names only, never user text.
- Audit changes with `logs.action(...)` after success (see `portcullis-feature-scaffold`).
- Tests: `FakeUpstream` (`upstream` fixture) for the proxy, `FakeServerTools` for server calls. Run the nearest file only.

## Where the details are

- Stronghold routes, turn engine, memory, skills, tickets: `apps/stronghold/README.md`.
- Proxy and security model: `apps/portcullis/README.md` ("Security model", "Internal API").
- Agent and delegation events: `apps/legion/README.md` ("Orchestrator").
