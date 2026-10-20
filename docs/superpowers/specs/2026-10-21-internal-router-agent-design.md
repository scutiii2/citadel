# Internal Router agent

Date: 2026-10-21 (Asia/Manila)
Implementation: 2026-10-21, subsequently authorized by the user.
Status: Implemented and validated on `codex/internal-router-agent`; the user subsequently authorized local integration into `main`. Undeployed; live model evaluation remains pending.

## Intent

Create a dedicated internal Router agent that chooses which agent should handle
a request and which model tier fits it. Reuse Triage Assistant's staged decision
flow: Laya English, Laya typed-decisions, narrowing when necessary, then Jev.
The Router is configurable on Ember Admin's existing Agents page and visible
on Ember Web's existing Agents page. Garrison validates and executes decisions.

The user subsequently authorized implementation. See the implementation plan
for verification evidence and remaining live evaluation requirements. No
deployment or automation is activated by this document.

## Current implementation and reuse

- `apps/garrison/src/agents/auto_route.py` selects a tool-using specialist through
  `decision.ask_choice`; it currently uses the configured Jev chain directly.
- `apps/garrison/src/llm/auto_tier.py` selects a size and maps it to a model tier.
- `apps/garrison/src/llm/triage_flow.py` implements the staged local/fallback flow,
  including model-specific thresholds, narrowing, uncertainty and trace output.
- `apps/garrison/src/llm/laya_provider.py` validates typed requests and supplies
  both local checkpoints. Choice questions currently allow 2-10 options.
- `agents/title-writer.json` demonstrates an internal agent with
  `delegable=false`, no tools and no entry/orchestrator role.
- Agent Store validates Admin changes and saves deployment-specific overrides
  in `.data/agent_overrides.json`; the supervisor applies process changes.
- Ember API owns agent discovery and Admin proxies. Ember Web lists defined
  agents, including offline and disabled agents, without exposing their URLs.

Use the existing lifecycle, registry, MCP transport, trusted identity, usage,
cancellation and frontend controls. Check the catalog before implementing any
new reusable building block. Keep each project's code self-contained.

## Chosen architecture

Add `apps/garrison/agents/router.json` as a supervised internal agent with a
stable ID of `router` and label `Router`. Allocate an unused port when implementing;
do not reserve a port by editing runtime files today.

Add a typed `internal_role` agent field, absent by default and accepting `router`
for this version. Add an optional `decision` policy block for Router agents.
At most one enabled agent may have that internal role. The role is separate from
`entry`, `orchestrator` and `delegable`; existing agents keep their current behavior.

Enforce these Router invariants on every file/Admin write and at startup:

- `entry=false`, `orchestrator=false`, `delegable=false`.
- `memory_recall=false`, `plan_tool=false`, tool deny list contains `*`.
- Local execution uses the existing Laya provider/local gateway and the two
  supported checkpoints, rather than adding an invented provider name.
- No private extension discovery, tool execution, answer generation, delegated
  work or recursive routing occurs inside the Router.

Expose a dedicated internal `route` operation on the Router's existing MCP
endpoint. Garrison calls it directly; it is absent from assistant-facing tool
catalogs and the browser proxy allowlist. Internal authentication is required.
Caller URLs, credentials and arbitrary provider names are never model arguments.
Ordinary ask/interpret operations on a Router-role agent refuse use as a chat
assistant. Its status and administrative operations remain available.

The Router invokes the shared triage implementation in its own process. It does
not delegate to the running triage-assistant agent. Build request-local triage
policy snapshots so Router settings cannot mutate Triage Assistant's policy.
Serialize access to model state where required by the current Laya implementation;
the overall deadline includes waiting for that work.

Alternatives considered: reuse helpers inside the entry agent (less process cost,
but lacks the desired dedicated lifecycle); delegate routing through Ember's
normal tool loop (adds model work and recursive-delegation risks). The supervised,
directly called internal agent provides the requested independent configuration.

## Configuration on Ember Admin's Agents page

Keep the existing `agents.manage` permission and agent override/reset workflow.
The Router card has an Internal / Router badge, effective policy summary, and
normal running/offline/disabled state. Editing provides the following controls:

| Setting | Initial value / rule |
| --- | --- |
| Enabled | On in the shipped Router definition; deployment override can disable it. |
| Label, port, advertised URL | Existing validated agent controls. |
| Choose specialist | On. Off leaves the request with Ember. |
| Choose model tier | On. Off preserves explicit or configured default tiers. |
| Local voters | English and typed enabled, in that order. |
| Jev fallback | On, through the existing `triage` backend chain and credentials. |
| Confidence thresholds | Existing triage defaults by voter and option count. |
| Narrowing | Existing prune ratio 0.25 and pair ratio 0.5; retain the three-round cap. |
| End-to-end deadline | 10 seconds; valid range 1-30 seconds. |
| Remote-call timeout | 3 seconds, bounded by remaining end-to-end time. |
| Size-to-tier mapping | tiny/everyday -> light; large -> standard; hardest -> heavy. |
| Decision trace | Off; enable structured trace metadata for diagnostics. |

Thresholds use 0-1 consistently in the Admin form and backend contract; they are
not labeled as measured accuracy. At least one local voter or a remote
fallback path must be enabled. Missing credentials report a degraded policy,
not a fake ready state. Existing checkpoint availability checks report missing
models without silently downloading weights or installing dependencies.

Only controls that affect Router behavior appear in its form. Entry,
orchestrator, tool scopes, free-form persona and chat token knobs are replaced
with read-only role explanations rather than editable settings that do nothing.
The supported local models and remote fallback chain are identified separately.
Secrets remain deployment-managed; this feature adds no API-key editor.

Save is explicit. Validation precedes persistence; busy/error states retain the
draft. The supervisor starts/restarts/stops the Router using the existing
override mechanism. New requests use the new configuration after that process
is ready. Requests affected by a restart fall back as described below. Reset
restores tracked defaults. Disabling or removing the Router is allowed and
must leave ordinary chat working.

## Request and decision contract

Garrison builds the input from the actual per-request roster, effective tool
availability, caller permissions and selected settings. The Router receives:

- The user message, plus at most the last 600 characters of the previous
  assistant message as labeled context. Exclude Memory injection, hidden prompts,
  raw tool results, credentials and full conversation history.
- Candidate IDs, labels and focus descriptions capped at 240 characters each.
  Candidates are the tool-using specialists routable today; tool-less helpers,
  internal agents and orchestrators are excluded.
- The entry agent as the explicit `none` choice, so ordinary questions can stay
  with Ember.
- Each target's actual allowed tier names and size guidance, an explicitly
  requested tier if present, enabled decision tasks and an opaque request ID.

Send typed choice questions to the triage flow: one for the agent and one for
request size. Size choices remain tiny, everyday, large and hardest. Map size to
a tier only after validating the selected target's available tier range.
Routing and size outcomes carry independent confidence and uncertainty flags.
One uncertain outcome must not invalidate an independently settled outcome.

Example response shape (illustrative names, not a new agent definition):

```json
{
  "agent": {
    "choice": "server-ops",
    "confidence": 0.88,
    "uncertain": false,
    "answered_by": "laya-typed"
  },
  "size": {
    "choice": "large",
    "confidence": 0.82,
    "uncertain": false,
    "answered_by": "laya-typed"
  },
  "model_tier": "standard",
  "policy_revision": "opaque-revision",
  "usage": []
}
```

`confidence` is the triage flow's reported score. Garrison treats
`uncertain=true`, `unknown`, invalid IDs and malformed results as abstention,
even when a provisional choice has a high numerical score. Trace output cannot
turn a provisional answer into an execution decision. The response includes
structured per-voter usage; the example leaves it empty for brevity.

## Bounds and conservative behavior

Keep the existing triage 10-option limit. A roster of at most nine specialists
plus `none` fits. With a larger roster, abstain from specialist selection and let
Ember choose from the full roster; size classification can still run. This version
does not silently truncate or preselect specialists to fit the window.

The local path accepts at most 4,000 characters of subject text. Larger subjects
may use the existing Jev long-input path, bounded by 16,000 characters, only when
fallback is enabled and available. Longer subjects abstain. Never truncate away
part of a user's request merely to obtain a confident classification. Overlong
typed criteria likewise produce abstention rather than dropping candidates.

Use existing model-specific thresholds and narrowing semantics. Any final
triage result marked uncertain is advisory only. Do not lower all thresholds
to the current direct-Jev 60% setting. Bound the complete sequence by the Router
deadline, not just each individual remote call. Cancellation detaches local
work safely if inference cannot be interrupted; late results cannot dispatch
work or attach to a different request.

## Garrison integration and fallback

1. At the top-level entry/orchestrator turn, establish trusted caller context,
   cancellation, approvals and actual available candidates before calling Router.
   Route once per top-level turn; delegated and internal calls never invoke it.
2. Skip the agent-choice task when delegation would require approval or is denied.
   Ember retains its normal approval-aware delegation path. Tier selection may
   still run if allowed and no tier was explicitly requested.
3. Validate the response against the original snapshot and recheck current
   target availability/authorization before dispatch. Reject another internal
   agent, an unknown target or any returned URL.
4. A settled specialist choice uses existing delegation dispatch, progress,
   attachment handling and identity propagation. Pass the validated tier to that
   target; its own limits and explicit caller settings remain authoritative.
5. `none` or an uncertain agent choice keeps the turn with Ember. A settled size
   can still select Ember's tier. An uncertain size keeps the chosen target's
   configured default. Explicit caller tiers always win and remain validated
   against the target's limits.
6. A missing, disabled, offline, timed-out or failed Router, invalid contract or
   absent local/remote model causes normal Ember orchestration with configured
   default tiers. A short follow-up under 20 characters with history abstains
   from tier selection, preserving current auto-tier behavior.
7. Once specialist work begins, retain today's behavior: report its failure
   rather than retrying through Ember and risking repeated external actions.

Keep user messages and stored chat history unchanged. Router processing must
preserve all existing attachment/table references, private-extension isolation,
planning controls, model limits and tool-approval behavior.

## Ember Web Agents page and observability

Extend agent definition/registry/listing metadata with the internal role and a
sanitized decision-policy summary. Older records without them remain valid.
The Router appears on the existing Agents page even when disabled or offline,
with an Internal / Router badge, a plain purpose description, status, local model
information and Jev fallback state. It remains unavailable as a chat destination
or delegable specialist. No server URL, credential or full policy trace is public.

Record Router work as Router usage rather than as an entry-agent model call.
Include actual local checkpoint and remote backend/model provenance, token usage
where available, elapsed time, settled/abstained outcome and reason. Record all
attempted voter calls, including partial work before a timeout; avoid counting
them again in entry usage. Existing delegated answer usage remains unchanged.

The chat progress stream can show a compact routing step and completion outcome
using existing event rendering. It must not stream Router JSON as the answer.
Trace diagnostics contain IDs, thresholds, probabilities and outcomes, without
duplicating user text into new application logs. Existing chat/usage visibility
permissions continue to apply. A model's configured availability and an actual
successful remote call remain distinguishable.

## Migration, affected areas and implementation limits

The Router becomes the sole automatic agent/tier decision path in the new
implementation. Retire calls to legacy direct `auto_route`/`auto_tier` decision
classification so the same request is not classified twice. Retain shared
delegation helpers, tier resolution, Jev backend chain and triage implementation.
Old `classifier.auto_route`, `classifier.auto_tier` and feature-specific chains
remain accepted as deprecated, non-authoritative configuration for compatibility;
document their replacement and remove them from shipped examples when appropriate.
The Router's enabled switch and per-task settings govern activation, including
when it is offline; legacy Jev routing must not reactivate implicitly.

Expected implementation areas:

- Garrison: agent definition/validation/store/supervisor metadata, Router's
  internal operation and client, request-local triage policy, cancellation,
  routing integration and accurate usage collection.
- Ember API: agent directory/listing metadata, Admin validation/proxy contracts
  and Router usage compatibility. Preserve existing `agents.manage` gates.
- Ember Admin: existing Agents cards/form/client, validated Router controls,
  save/reset lifecycle and effective state.
- Ember Web: existing Agents listings/cards/client and progress compatibility.
- Documentation and CLI: agent/routing configuration and event/usage contract
  compatibility. No new CLI agent picker or direct Router command.

Follow the existing Ember tokens, shared controls and layouts. Implementation
will require the relevant Ember UI skills. Keep this work independent of the
Obsidian/Notes promotion design and make no changes to those features.

## Acceptance and validation

- Router is a supervised, independently configurable agent visible in both
  Agents pages, including disabled/offline states. Ordinary agents round-trip
  unchanged through Admin edits; Router's enforced role cannot gain tools,
  become entry/orchestrator or enter a delegation roster.
- Admin changes require `agents.manage`, are audited without user message text,
  persist only as deployment overrides, validate before saving, and support reset.
- Internal operation rejects unauthenticated calls and stays outside browser and
  model-facing tool access. Decisions cannot name targets outside the live roster.
- Compare direct-Jev and staged triage against representative labeled routing
  and tier cases; record selected agents/tiers, abstentions, latency and remote
  calls before enabling in a deployed instance. Do not claim accuracy gains from
  confidence scores alone.
- Cover local success, local disagreement, narrowing, Jev fallback, unavailable
  models/keys, uncertainty, malformed responses, overlarge rosters and inputs,
  end-to-end deadline, cancellation and concurrent requests.
- Verify no recursive routing or double classification, explicit tier precedence,
  tier clamping, default fallback, approvals, disabled tools, attachment handoff,
  partial voter accounting and unchanged specialist failure handling.
- Run focused Garrison tests plus relevant agent/spec/store/triage/delegation
  regressions; Ember API directory/Admin/usage tests; Admin and Web type checks,
  builds, affected unit tests and focused browser flows. Verify CLI event parsing.

## Next session

Review this specification and any requested amendments, then write the
implementation plan before product changes. This document does not authorize
committing, pushing, deployment, downloading model weights or scheduling work.
