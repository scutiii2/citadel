# Internal Router Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execution: native implementation in the isolated `codex/internal-router-agent` worktree, authorized by the user.

**Goal:** Ship an internal triage-based Router that chooses a specialist and model tier, is configurable in Ember Admin, and is visible in Ember Web.

**Architecture:** Add a non-delegable Router role to Garrison's existing supervised agents. A trusted internal MCP operation evaluates typed questions using request-local triage policy; the entry agent validates its decisions before existing delegation or tier resolution. Publish sanitized role/policy metadata through existing discovery and Admin interfaces.

**Tech Stack:** Existing Python/FastMCP/AnyIO, FastAPI, Vue 3/TypeScript, Vitest and Playwright; no new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-internal-router-agent-design.md`

## Global Constraints

- Stable agent ID `router`, label `Router`; choose an unused port during execution.
- `entry=false`, `orchestrator=false`, `delegable=false`, `memory_recall=false`, `plan_tool=false`, deny `*`.
- Existing Laya local provider, supported English and typed checkpoints, optional existing Jev triage chain.
- Confidence uses 0-1. Preserve triage's voter/count thresholds, prune ratio 0.25, pair ratio 0.5 and three-round cap.
- Deadline 10 seconds, configurable 1-30; remote timeout 3 seconds, bounded by time remaining.
- Local subject limit 4,000 characters; remote subject limit 16,000; previous assistant context at most 600 characters; focus at most 240 characters.
- At most nine specialists plus `none`; larger rosters abstain from agent selection without dropping candidates.
- Size mapping: tiny/everyday -> light; large -> standard; hardest -> heavy. Explicit caller tier wins, subject to target validation.
- Short follow-ups under 20 characters with history skip size selection.
- No model downloads, secret-file reads/printing, deployment, commit or push as part of implementation without subsequent authorization.
- Preserve existing approvals, identity, attachments, model caps, private-extension isolation, account permissions and ordinary agent configurations.
- Obsidian/Notes work remains outside this plan.

## Review Focus

1. An uncertain agent outcome and a settled size outcome must still allow Ember to use the settled tier (Task 4).
2. Admin restarts Router during a request: that request falls back once; new requests discover the new process (Tasks 3-4).
3. Explicit tiers unsupported by a chosen target must follow existing tier validation rather than be silently substituted (Task 4).
4. Queued/cancelled local inference can finish late: it cannot dispatch work, cross request identity, or alter completed accounting (Tasks 2-4).
5. Editing an ordinary agent must preserve unknown supported fields and must not acquire Router-only invariants (Tasks 1 and 6).

## Preparation and execution rules

- Obtain review of this plan and execution-method selection before product changes.
- Check isolation using `git rev-parse --git-dir`, `--git-common-dir` and `--show-superproject-working-tree`. Current checkout is `main` in the primary workspace, with two untracked specs; preserve both.
- Follow the worktree skill at execution time. Obtain the user's worktree preference before creating one; if used, place it under an ignored project-local directory and use a `codex/` branch. Copy the approved untracked spec/plan into it without moving or deleting the originals.
- Check catalog_service (`GET http://localhost:8020/catalog`, bounded timeout), then its documented cache. The cache was absent during planning; a service miss permits existing source-based reuse. Do not start new services merely to plan.
- Locate existing Python environments and frontend dependencies without installing or downloading anything. Establish baseline using the regression groups below; report existing failures distinctly.
- Use test-first cycles for behavior changes. Run the target failing tests, implement, then rerun the owning regression group. Keep plan checkboxes current. Do not commit between tasks unless the user asks.

## Task 1: Typed Router policy and supervised role

**Files:** Create `apps/garrison/src/agents/router_contract.py`, `apps/garrison/agents/router.json`, `apps/garrison/tests/test_router_contract.py`. Modify `apps/garrison/src/agents/agent_spec.py`, `agent_store.py`, `agent_registry.py`, `agent_routing.py`, `apps/garrison/src/supervisor.py`, and their existing tests.

**Interfaces:**

- `RouterPolicy`: immutable validated policy with `choose_agent`, `choose_tier`, `english`, `typed`, `fallback`, `thresholds`, `prune_ratio`, `pair_ratio`, `deadline_seconds`, `remote_timeout_seconds`, `size_tiers`, `trace`. Defaults are the spec values; voters and task switches default true, trace false.
- `RouteCandidate`: ID, label, focus and existing tier descriptors. `RouteRequest`: subject, candidates, entry target/tier descriptors, optional explicit tier, `choose_agent`, `choose_tier`, `request_id`.
- `DecisionOutcome`: choice or null, confidence 0-1, uncertain, answered_by, reason. `RouteResponse`: independent agent/size outcomes, optional model_tier, policy_revision, per-voter usage and optional sanitized trace.
- Extend `AgentSpec` with `internal_role: str | None` and `decision: RouterPolicy | None`; serialize policy to the existing JSON override shape.

- Write `test_router_policy_defaults_and_bounds`: assert deadline=10, remote timeout=3, invalid 0/31 deadlines, NaN confidences, unknown policy keys, invalid size/tier names and all voters/fallback disabled are rejected.
- Write role tests: reject tools, entry/orchestrator/delegable, memory/plan flags and unsupported provider/gateway; reject two enabled Routers in set-wide validation, including Admin overrides.
- Write ordinary-agent round-trip, Router reset/disable, non-delegation-roster and registry-definition role/policy metadata tests.
- Run the new and existing spec/store/supervisor/registry/routing tests and confirm the new assertions fail before implementation.
- Implement the typed contract, role validation, policy serialization and supervisor metadata. Default old definitions to no internal role; reject `decision` on unrelated agents. Publish only sanitized policy summaries.
- Create the tracked Router definition with an unused configured port. Check port uniqueness from safe agent JSON files; no runtime startup yet.
- Run `python -m pytest -q tests/test_router_contract.py tests/test_agent_spec.py tests/test_agent_store.py tests/test_supervisor.py tests/test_agent_registry.py tests/test_agent_routing.py` in `apps/garrison` using its environment; require all passing or identify pre-existing failures.

## Task 2: Request-local triage policy, deadline and voter accounting

**Files:** Modify `apps/garrison/src/llm/triage_flow.py`, `laya_provider.py`, `decision.py`; create `apps/garrison/src/agents/router_engine.py`, `apps/garrison/tests/test_router_engine.py`; extend `tests/test_decision_strategy.py` and `test_triage_flow_provider.py`.

**Interfaces:**

- Extend `TriageFlow` with optional immutable settings snapshot, deadline/cancellation check and per-voter completion observer. Existing callers that omit them retain current behavior.
- Extend fallback choice execution with an optional settings snapshot, remaining-time timeout and attempt observer; do not mutate the globally cached `decision.settings()`.
- `RouterEngine.route(request: RouteRequest, policy: RouterPolicy) -> RouteResponse` owns one request's outcomes and usage. It uses injected local voters/backend adapters in tests.
- Voter usage records contain actual backend/model, measured start/end/duration, known tokens, success/failure and abstention reason. Unknown token counts remain unknown. Do not fabricate tokens for failed calls.

- Write tests for English success, typed agreement, disagreement/narrowing, Jev success, uncertain final outcome and separate outcomes for the two questions.
- Assert existing triage tests remain unchanged under default policy; two concurrent Router policy snapshots cannot influence each other or normal triage.
- Write bounds tests: 10 specialists abstain only from agent choice; >4,000 subject uses authorized fallback; >16,000 abstains; oversized criteria never truncate candidates; no available backend yields abstention.
- Write deterministic clock tests for deadline including queued model locks, timeout clamped to remaining time, cancellation between voters, and no new calls after deadline.
- Write accounting tests for every local/remote attempt, repeated narrowed rounds, classifier-chain failures and partial completion before cancellation. Freeze completed response accounting so a late worker cannot change it.
- Run the new tests to confirm failures, then implement policy injection and the engine. Preserve current triage algorithm; use request-local inference window settings and model locks rather than changing shared voter settings during concurrent requests.
- Run `python -m pytest -q tests/test_router_engine.py tests/test_decision_strategy.py tests/test_triage_flow_provider.py tests/test_laya_provider.py tests/test_decision.py` in `apps/garrison`.

## Task 3: Internal route operation and bounded client

**Files:** Create `apps/garrison/src/agents/router_client.py`, `apps/garrison/tests/test_router_server.py`, `test_router_client.py`; modify `apps/garrison/src/server.py`, `core/internal_auth.py` as needed, `tests/test_server.py`, `test_internal_auth.py`.

**Interfaces:**

- Internal MCP `route(request: dict, ctx: Context) -> dict` exists on Router-role processes only, validates RouteRequest and returns RouteResponse.
- `async router_client.decide(request: RouteRequest) -> RouteResponse | None` resolves the enabled Router from trusted registry metadata and calls it with internal authentication/current requester headers.
- Client returns no decision on absent/stale/multiple Router entries, transport failure, invalid response, deadline or cancellation. It never accepts an address from the Router response.

- Test missing/wrong tokens, including the empty configured-token case: the Router operation fails closed even though generic middleware currently permits tokenless local deployments.
- Test ask/interpret refusal on Router, ordinary-agent route refusal, route omission from assistant-facing tools, and authenticated status/Admin compatibility.
- Test typed transport round-trip, requester propagation, stale process discovery, connection timeout, malformed JSON, invalid target values, cancellation and late response rejection.
- Run tests red, then implement the operation and client using existing MCP session/identity conventions. Skip private-extension/tool setup inside Router. Keep routing progress free of decision JSON and user text.
- Handle local inference asynchronously via a bounded worker; cancellation stops scheduling further voters. Obtain per-voter completion accounting through a request-scoped collector; completed/late records stay tied to that request.
- Run `python -m pytest -q tests/test_router_server.py tests/test_router_client.py tests/test_server.py tests/test_internal_auth.py tests/test_private_server.py` in `apps/garrison`.

## Task 4: Entry routing, tiers, fallback and usage integration

**Files:** Modify `apps/garrison/src/agents/agent_config.py`, `auto_route.py`, `delegation.py`, `apps/garrison/src/llm/base_provider.py` if required by additive usage metadata, and `apps/garrison/src/core/usage_log.py`; create `tests/test_router_integration.py`; update `tests/test_auto_route.py`, `test_agent_config.py`, `test_live_usage.py`, `test_usage_log.py`.

**Interfaces:**

- Replace entry calls to direct classifier routing/auto-tier with one `router_client.decide` call per eligible top-level orchestrator turn.
- Reuse specialist dispatch helpers; accept validated Router outcomes rather than call Jev again. Extend dispatch arguments with model_tier only when valid.
- Use existing `delegated_usage` collection for Router voter rows, attributed to agent ID `router`, separate from entry and specialist model usage. Additive metadata must survive API/CLI parsing.

- Test settled specialist + size dispatch once, no classifier duplication, `none` + settled size on Ember, uncertain agent + settled size, and settled agent + uncertain size/default.
- Test explicit caller tier precedence and unsupported explicit tier using existing resolution errors; derived tiers obey target range. Preserve reasoning-effort behavior.
- Test skip on delegated/internal turns, approval-required/denied agent choice with independent tier choice, disabled tools/targets, overlarge rosters, short follow-ups, stale Router process and offline/default fallback.
- Test cancellation before/after routing, unchanged attachment/table references and private extension state, and specialist failure reported once without rerouting.
- Test actual per-voter usage attributed once to Router even when routing abstains or times out; entry does not masquerade as a classifier call. Bound partial-record reporting without extending request deadline.
- Run tests red, implement integration, and leave deprecated direct configuration parsers readable but inactive. Disabling/deleting Router must not reactivate legacy Jev routing.
- Run the Garrison suite with `python -m pytest -q`; record unrelated baseline failures separately. Re-run only changed/failing groups when further edits require it.

## Task 5: Ember API discovery, proxy protection and accounting

**Files:** Modify `apps/Ember/ember_api/src/services/agent_directory.py`, agent listing response declarations found through `/api/agents`, `services/agent_admin.py` only where contract changes require it, and existing turn/usage parsing as needed. Extend `tests/test_agent_directory.py`, `test_agent_admin.py`, `test_agent_gateway.py`, `test_agent_events.py`, `test_mcp_proxy.py`, and relevant `test_usage_*` tests.

**Interfaces:**

- Add optional `internal_role` and sanitized `decision` summary to definitions and AgentListing. Older registries/listings remain parseable.
- Admin agent JSON round-trips the policy through existing routes; validation is authoritative in Garrison. Existing `agents.manage` requirement/audit remains intact.
- Browser agent proxy explicitly refuses internal `route` regardless of schema visibility. Existing allowlisted status behavior remains intact.

- Test running/offline/disabled Router listing, old registry compatibility, secret/URL/trace exclusion and ordinary-agent listing stability.
- Test Admin 401/403, successful policy save/reset, backend validation errors, role field preservation and failed-save auditing behavior.
- Test that browser proxy refuses route, ask and interpret access to Router where applicable; direct internal route stays backend-only.
- Test Router voter usage grouping/detail, partial usage rows and no double billing under existing summary/answer semantics.
- Run tests red, implement minimal additive contracts/accounting, then run `python -m pytest -q tests/test_agent_directory.py tests/test_agent_admin.py tests/test_agent_gateway.py tests/test_agent_events.py tests/test_mcp_proxy.py` plus changed usage tests in `apps/Ember/ember_api`.

## Task 6: Ember Admin Router controls

**Files:** Modify `apps/Ember/ember_admin/src/api/AgentsAdminClient.ts`, `components/admin/AgentForm.vue`, `AgentAdminCard.vue`, `views/AgentsAdminView.vue`; create `components/admin/RouterPolicyForm.vue` and its Vitest test. Extend `views/AgentsAdminView.test.ts`, `e2e/fakeApi.ts` and create `e2e/router-agent.spec.ts`.

**Interfaces:**

- Typed `RouterPolicy` and optional role/decision metadata in AgentConfig. `RouterPolicyForm` edits only policy via typed model binding, with errors/busy state owned by AgentForm.
- Existing Save/Reset/Delete/enable controls remain the lifecycle entry points; role-specific fixed fields are read-only. No new page or navigation item.

- Test default policy, task/voter switches, 0-1 thresholds, 1-30 deadline, remote timeout, tier mapping, invalid config, dirty state and failed save retaining edits.
- Test enforced-role read-only explanation, local models vs fallback labels, unavailable-key/model states, disable/reset and ordinary-agent round-trip preserving supported unseen fields.
- Run tests red, then implement with existing ToggleSwitch, BaseModal, buttons and tokens. Do not display an optimistic enabled/running state before confirmed persistence/readiness.
- Add a fake-API browser flow editing/saving/resetting/disabling Router and a failed-save flow; keep existing agent-gateway flows passing.
- Run `npm test -- src/views/AgentsAdminView.test.ts src/components/admin/RouterPolicyForm.test.ts`, `npx vue-tsc -b`, `npx vite build`, then `npm run test:e2e -- e2e/router-agent.spec.ts e2e/agent-gateways.spec.ts` in `apps/Ember/ember_admin`. Run relevant radius/token checks from its existing tests. Use existing browser test setup, no separate browser agents.

## Task 7: Ember Web visibility and CLI compatibility

**Files:** Modify `apps/Ember/ember_web/src/api/AgentsClient.ts`, `components/AgentCard.vue`, `views/AgentsView.vue`; extend `views/AgentsView.test.ts`, `e2e/fakeApi.ts`; create `e2e/router-agent.spec.ts`. Inspect `apps/Ember/ember_cli/src/events.py` and its existing tests for additive event/usage compatibility.

**Interfaces:** AgentListing carries optional internal_role and safe decision summary. Router card shows Internal / Router, running/offline/disabled state, supported local models and fallback readiness, with no chat/select/delegate action.

- Test all Router states, safe model/fallback summary, old listings without metadata, role badge, unchanged normal cards and summary counts.
- Test routing progress does not become answer text and unknown additive usage metadata does not break web/CLI consumers.
- Run tests red, implement with existing AgentCard/token patterns, and add a focused Agents page browser flow using fake API.
- Run `npm test -- src/views/AgentsView.test.ts`, affected progress tests, `npx vue-tsc -b`, `npx vite build`, `npm run test:e2e -- e2e/router-agent.spec.ts` in `apps/Ember/ember_web`; run the CLI's existing event/usage tests using its configured environment.

## Task 8: Evaluation, documentation and final review

**Files:** Create `apps/garrison/scripts/check_router_cases.py`, `tests/test_check_router_cases.py` and `apps/garrison/docs/router-evaluation.md`. Update `apps/garrison/README.md`, `configs/config_tuning.json.example`, relevant Ember READMEs, and the spec status after implementation evidence exists.

- Define labeled cases for general questions, specialist questions, ambiguous follow-ups, mixed/multistep work, tier complexity, attachments, restricted rosters and overlarge inputs.
- Implement `--offline` fixture evaluation (default) and explicit `--live` comparison modes. Live mode compares direct Jev and Router using the same subject/candidates, reports selected agent/tier, abstention, elapsed time and remote-call count; it does not execute specialist work or write user data.
- Test evaluator aggregation with fake backends; run offline evaluation and record actual results. Do not claim measured accuracy from fixtures. Run live comparison only with an authorized configured runtime; absence of that evidence blocks deployment enablement, not offline implementation review.
- Document Router lifecycle/policy, local prerequisites, key readiness, conservative limits, legacy-setting deprecation, fail-closed internal transport and disabling/default fallback.
- Check changed-contract tests across Garrison/API/Admin/Web/CLI, focused browser flows, type checks and builds. Report exactly what ran, passed, failed or remained unavailable.
- Review the complete diff against spec acceptance, permission/cancellation/usage invariants and unrelated edits. Obtain independent review only under the chosen execution workflow; do not invent a model override.
- Run `git diff --check`, inspect `git status --short`, and report changes with verification evidence. Leave files uncommitted and deployment unchanged unless separately authorized.

## Implementation and verification record — 2026-10-21

The task descriptions above retain the planned checks as reference, rather than
claiming that every suggested individual test was added. The delivered scope and
observed evidence are recorded here.

- [x] Tasks 1–4: typed policy, supervised Router on port 9117, request-scoped triage,
  internal authenticated transport, entry routing and actual voter accounting.
- [x] Task 5: additive safe API discovery, status-only browser proxy and Router
  usage/trace parsing; existing Admin authorization and persistence reused.
- [x] Task 6: Router policy controls on Admin Agents, fixed role restrictions,
  failed draft retention and live readiness metadata.
- [x] Task 7: Internal / Router listing in Web for running/offline/disabled agents;
  existing progress and usage consumers retained.
- [x] Task 8: offline fixture evaluator, operational documentation and independent
  diff review. No remaining P1/P2 findings were reported after fixes.

The catalog service was unavailable and its documented cache was absent; existing
source implementations were inspected and reused. Existing Python environments
and frontend dependencies were reused without installing packages. All product
changes are isolated in `.worktrees/internal-router-agent`; the primary checkout's
original untracked specifications remain in place.

Final verification:

- Garrison: full `python -m pytest -q`: **1,210 passed**, eight existing MCP SDK deprecation warnings.
  The first final run exposed a stale example-config assertion expecting retired
  automatic routing settings; it was updated to assert active keys while ensuring
  legacy parsers remain readable. Two existing agent-spec fixtures referring to
  retired `apps/mcp_server` paths now refer to `apps/armory`.
- Ember API: 161 tests passed in the broader affected regression group; the final
  discovery/gateway/events/proxy/Router usage group passed **83 tests**.
- Ember Admin: full Vitest suite **481 tests passed**; final affected group
  **26 tests passed**. `vue-tsc -b` and `vite build` passed after readiness changes.
- Ember Web: full Vitest suite **2,077 tests passed**; final Agents group
  **10 tests passed**. `vue-tsc -b` and `vite build` passed after readiness changes.
- Playwright: Admin Router and existing gateway flows **2 passed**; Web Router
  running/offline/disabled listing flow **1 passed**. Admin flow covers explicit
  saves, failed draft retention, widths 1280/768/375 and light/dark presentation.
- A real loopback MCP session with an injected fake engine passed the authenticated
  structured-response and trusted requester-header transport test. No model calls.
- Eight synthetic offline evaluation fixtures passed with zero remote calls.
  This establishes plumbing behavior, not classifier accuracy.

Independent review found and resolved unknown explicit-tier validation, possible
uncached model downloads, and missing degraded readiness metadata. Router now
passes only verified absolute cached model directories to Laya; Hub resolution
uses `local_files_only=True` and `token=False`. Installed Laya 0.4.9 revision and
path-loading code was inspected to confirm the guarded path avoids downloads.

Limits and follow-up validation:

- Live Router versus Jev accuracy/latency evaluation remains pending. No live
  classifier calls or model downloads were made. This is a deployment gate.
- CLI event/render tests could not run because the existing Python environment
  lacks `rich`; no CLI environment or dependency installation was introduced.
  CLI source did not change. Web/API usage/progress regression groups passed.
- The user subsequently authorized committing, rebasing onto `main` and local integration. No running deployment was changed.

Historical diagnostic references updated for Legion v2: the retired voter-comparison diagnostic is covered by decision-strategy tests and router contract cases.
