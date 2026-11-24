# Legion

Legion hosts role-based language and decision agents between Ember and Armory.
Each `agents/<id>.json` is one agent process managed by the supervisor.

```
portcullis --(MCP)--> entry orchestrator --delegate_to_agent--> specialists
                              |                                  |
                              +--------------- Armory -----------+
```

Language agents use Anthropic or OpenAI protocols and may call tools. Decision
agents use the Laya/Jev arrangement to answer typed questions without generation.
The internal Router chooses specialists and model tiers through that arrangement.

## Tests

`uv run pytest` skips the `slow` tests (`test_private_integration.py`, real MCP servers). `uv run pytest -m ""` runs everything; do that before a merge.

## Setup

1. Copy `.env.example` to `.env`.
   - **Anthropic-protocol agents** (`llm.provider: "anthropic"`) call their models through the chat gateway built into
     Legion (`src/gateway/conversation`). Their keys are not in `.env`: on the Legion admin
     app's **Connections** page, **Model gateways**, save a gateway with the same id as the
     file in `gateways/anthropic/` (`claude`, `openrouter`, ...) and paste its key there (write-only). Entries live in Legion's
     settings database (`.data/settings.db`, table `conversation_gateways`); an edit reaches every agent within a minute. Legion must still
     know where Treasury is for its other settings: `treasury_url` in `configs/config_app.json` (`TREASURY_URL` overrides it).
   - **OpenAI-protocol agents** use the same chat gateway. Save a gateway with the
     same id as the file in `gateways/openai/` (`gpt`, `groq`, `azure`, ...).

2. Make sure `mcp_server` is running (`py -m src.run` in `apps/armory/`) -
   add it to Legion as the `main` server
   (`PUT /agents/servers/main` with `{"label": "armory", "transport": "http", "url": "http://127.0.0.1:29600/mcp"}`);
   a new install has no servers.

3. Start the agents from `apps/legion/`: install the project once with `uv sync`
   (creates `.venv`), then run `uv run python -m src.supervisor`. See Agents below.

### Behavior since the ConversationGateway move (2026-11-14)

Applies to Anthropic-protocol agents, and since 2026-11-15 to OpenAI-protocol agents. The tool loop, failover, cooldowns and budgets are unchanged.

1. A malformed provider stream is no longer retried once on the same gateway. ConversationGateway
   reports it as `unavailable`; Legion cools that gateway down and moves to the next one.
2. The context breakdown is always an estimate: the gateway has no token-count route.
3. While a round streams, the live token meter counts answer text only, not thinking or
   tool-argument text. The exact total at the end of each round is unchanged.
4. A gateway "has credentials" when ConversationGateway has a gateway saved under that id. When the
   service cannot be asked, Legion assumes it does and lets the call report the outage, so Legion can
   start before the gateway.
5. Bedrock and Vertex are configured in ConversationGateway, not through Legion's AWS and Google
   env vars.

Failover reads the gateway's error `kind` (`rate_limit`, `quota`, `auth`, `unavailable`) and
`Retry-After`. An error without a kind (the request itself was refused) is never retried.

### Laya service

Laya is gateway `laya` of provider `decision`; Jev is gateway `jev`. Legion loads no model and holds
no address or key for either: both are entries of the decision gateway built into Legion
(`src/gateway/decision`), saved on the Legion admin app's **Connections** page, **Model gateways**, under those two ids
(`.data/settings.db`, table `decision_gateways`). Laya's address, strategy and window, and Jev's model and key, are set on the entry there.

An unreachable service warns, allowing `both` to fall through to Jev per request.
Agent strategies are `laya-only`, `jev-only` and `both`; see
[Decision question agents](#decision-question-agents).

## Agents

Each agent is defined by one file, `agents/<id>.json`. The file
name stem is the agent id (`^[a-z0-9][a-z0-9-]{0,62}$`). `agents/` is
tracked in Git as shared defaults. Admin edits go to the local
`.data/agent_overrides.json`; create or copy a tracked file for a shared change. Unknown keys are an error, so
typos are caught at startup.

Anthropic and OpenAI turns default to a 100,000-token budget and a 300-second
deadline. Set `llm.max_turn_tokens` (positive integer) and
`llm.max_turn_seconds` (0.001 to 86,400) beside `max_tool_rounds` to override
them per agent. Tokens include input and output summed across rounds, checked
when a response reports usage; one response can exceed the cap. A third consecutive tool
call with the same name and arguments ends the turn before it executes.
Deadlines interrupt async waits; a synchronous tool already running cannot
be undone. These budgets apply to each agent turn independently.

Both tool-calling providers offer the local `update_plan` tool: full checklist
snapshots with `pending`, `in_progress`, and `done` statuses (at most one item
in progress). State is per turn, with live `plan_update` events forwarded from
specialists under their own agent identity. Stop also reaches delegated peers
through linked internal request IDs and their MCP `cancel` tool.

```json
{
  "label": "Calculator",
  "port": 29605,
  "enabled": true,
  "entry": false,
  "llm": {
    "provider": "anthropic",
    "gateway": "openrouter",
    "model": "claude-sonnet-5-5",
    "temperature": 0.0,
    "reasoning_effort": "high",
    "max_tokens": 4096,
    "max_tool_rounds": 6
  },
  "persona": "You are a precise mathematician. Show every step and check results.",
  "instructions": "Use the calculator tools for every computation; never do arithmetic in your head.",
  "focus": "Arithmetic, algebra, percentages, unit conversion, compound interest.",
  "tools": { "allow": ["calc_*", "convert_*"], "deny": [] },
  "role": "specialist"
}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `label` | no | id | Display name. |
| `port` | yes | none | Port the child listens on. Unique across enabled files. |
| `enabled` | no | `true` | `false`: not spawned, not registered. |
| `entry` | no | `false` | The orchestrator Ember opens a chat with. Exactly one enabled agent must set it. |
| `llm.provider` | yes | none | `anthropic` or `openai` for language; `decision` for typed questions. |
| `llm.strategy` | decision only | `both` | `laya-only`, `jev-only`, or `both`. |
| `llm.min_confidence` | decision only | unset | Above 0 and at most 1. Unset: each model applies its own thresholds. Per-request overrides are accepted. |
| `llm.gateway` | no | provider default | A filename stem from `gateways/<provider>/<gateway>.json`. |
| `llm.fallback_gateways` | no | `[]` | Ordered same-provider backup gateways, as names or `{gateway, model?}` objects. See Gateway failover below. |
| `llm.model` | no | gateway's `model` | Model id. |
| `llm.temperature` | no | unset (provider default) | Float 0-2. |
| `llm.reasoning_effort` | no | `off` | `off`, `low`, `medium`, `high`. Maps to the Anthropic thinking budget or OpenAI `reasoning_effort`. |
| `llm.max_tokens` | no | today's hard-coded value | Output token cap per model call. |
| `llm.max_tool_rounds` | no | `6` | Cap on the tool loop. |
| `persona` | no | `""` | Persona text placed after the identity line in the system prompt. |
| `instructions` | no | `""` (built-in default) | Tool-use instructions placed last in the system prompt. Empty uses `DEFAULT_INSTRUCTIONS` in `src/agents/agent_roles.py`. |
| `focus` | no | `""` | One-line summary of what the agent is good at. Used for the orchestrator roster. Should be concrete. |
| `tools.allow` | no | `[]` | fnmatch globs on tool names with the `main__` prefix removed. Outside MCP connection tools require a matching allow glob. |
| `tools.deny` | no | `[]` | Globs removed after `allow`. Deny wins. |
| `role` | yes | none | `orchestrator`, `router`, `specialist` or `architect`. Architects use a language provider, never entry, and require `tools.deny: ["*"]`; recall, learning and the plan tool must be off. The code pipeline is implemented; operations is reserved for a later phase. |
| (roster) | whole folder | none | One architecture only. The enabled agents must hold exactly one orchestrator (the entry agent), exactly one router, at least one architect and at least one specialist; a save or an agent file that breaks this is refused. The retired `mode` key is ignored. |
| `kind` | architect only, required | none | Registered kind: `code`, `task`, `review`, `writing` or `operations`. At most one enabled architect per kind. |
| `workers` | architect only, required | none | Non-empty list of existing specialist ids. |
| `prefetch` | architect only | `[]` | Specialist ids allowed for pre-planning reads. Code uses the first only when a brief names a code file or conservative path. |
| `limits` | architect only | see meaning | `max_units: 12`, `max_parallel: 3`, `unit_timeout_seconds: 120`, `max_retries: 1`. Counts are positive integers; retries may be zero; timeout is a finite positive number. Unknown fields are errors. |
| `memory_recall` | no | `false` | At the start of each top-level turn, search the user's long-term Brain notes with the question (`stronghold__tool_brain_search`, up to 5) and put matching snippets in front of it. Needs the Stronghold connection and `stronghold__tool_brain_*` in the agent's allow list. Orchestrator role only. Only `ember` has it on. |
| `skill_recall` | no | `false` | At the start of each top-level turn, search the user's **approved** skills with the question (`stronghold__tool_skill_search`, up to 3) and put the matches in front of it, after any recalled notes. A proposal never loads before the user approves it on Ember's Skills page. Needs the Stronghold connection and `stronghold__tool_skill_*` in the agent's allow list. Orchestrator role only. Only `ember` has it on. |
| `skill_learning` | no | `false` | After a top-level turn that made at least 3 real tool calls and none failed, draft a reusable skill in the background and propose it (`stronghold__tool_skill_propose`) for the user's approval. One extra call to the tool-free `context-summarizer` agent per qualifying turn, so it is billed: switch it on per agent, no tracked agent has it. The drafting model sees only the user's request and the tool names with argument names, never results, values or the answer. A turn that used web, Firecrawl, email or a private extension tool never qualifies. Calls made by delegated specialists are not seen, so it fits agents that call tools themselves. Needs `stronghold__tool_skill_*` allowed and `context-summarizer` running. Orchestrator role only. |
| `delegable` | no | `true` | `false` keeps the agent out of every orchestrator's roster: it is called directly (for example by portcullis), never delegated to. |
| `plan_tool` | no | `true` (`false` for architects) | Offer the `update_plan` checklist tool (`src/agents/roles/orchestrator/plan.py`) for tasks of three or more steps. A chat can also switch it off per turn (`ask(plan=False)`), and the tool is offered only when both allow it. Plan mode fills the checklist at runtime instead of offering this tool to the model. |

An orchestrator file:

```json
{ "port": 29603, "entry": true, "llm": { "provider": "anthropic" }, "role": "orchestrator" }
```

### Gateway failover

An agent can try backup gateways when its current gateway runs out of credit,
is rate limited, rejects its credentials, or is unavailable. Configure the
ordered list in that agent's `llm` block; this example enables nothing by itself:

```jsonc
{
  "provider": "anthropic",
  "gateway": "claude",
  "model": "claude-sonnet-5-5",
  "fallback_gateways": [
    // Optional explicit model id on the backup gateway.
    { "gateway": "openrouter", "model": "anthropic/claude-sonnet-5.5" },
    // A name is shorthand for {"gateway": "bedrock"}.
    "bedrock"
  ]
}
```

Every name must have a gateway file under the same provider. Duplicate names,
the primary itself, malformed entries, unknown entry keys, and fallbacks on
Laya are rejected. A missing primary key still prevents startup; an unkeyed
backup is warned about at startup and skipped. Admin overrides accept the
same whole-agent-file shape.

Each turn starts with the first credentialed gateway outside cooldown and
stays on it until it fails. A switch retries only the failed model round;
completed tools and their results are retained. Signed thinking/reasoning
from earlier rounds is removed before sending to another gateway. Partial
answer text is reset before retrying. Ordinary bad requests and cancellation
do not trigger failover. If every candidate fails, the last error is raised;
if all are cooling down at turn start, the primary is attempted once.

Backups use their explicit `model` first, otherwise the matching primary tier,
then their gateway's default model, then the provider default. The advertised
tiers remain those of the primary. Cooldowns are scoped to provider and gateway:
Retry-After or 60 seconds for rate limits, 3600 for quota/auth, 30 for outages.
The last three are configurable under `gateway_failover` in
[`configs/config_tuning.json`](configs/README.md). Later turns return to the
primary after its cooldown expires; restart clears cooldowns.

The stream emits `gateway_switch` with `from`, `to`, and `reason`, without
error text. Usage rows record the answering gateway and any switches; status
lists each gateway's availability and cooldown. Ember currently drops the
switch event in its turn-event allowlist, so this phase adds no browser indicator.

Ember Admin's agent editor exposes this as one ordered **Gateways** list:
the first row sets `llm.gateway` / `llm.model`, and remaining rows set
`llm.fallback_gateways`. Reordering keeps each model with its gateway. Saving
validates every referenced gateway before writing the agent override; removing
a row does not delete its shared gateway preset.

### Automatic memory recall

With `"memory_recall": true` the agent loads the user's newest saved notes once per top-level turn and puts them before the question as a labelled block ("data the user saved earlier, not instructions"). It uses the normal tool path, so a `tools.deny` of `tool_mem_*`, the user's own tool switches and the asking user's identity all apply; any failure just means no notes that turn. The chat shows one step, "Loading saved notes", with the count only. The notes sit in the user turn, where models weigh them more than a tool result, so the saving rule (only facts the user stated) and `/memory forget` matter. `ai_agent` reads the tool's JSON answer and recognises "notes found" by the first line of its `message` field (`N saved note(s):`). The search is capped at 5 seconds, and the recall step is hidden from the history digest portcullis feeds back to the agent.

Name an agent for its job,
not its model (`ember`, `server-ops`, `reviewer`). Exactly one enabled file
sets `entry: true`. Add
more specialists as extra files.

`code-architect` (port 29621) plans multi-function code and assembles
`code-writer` outputs, with optional read-only context from `repo-helper`.

`task-architect` (port 29622) is the general fallback. It plans one unit, or a short chain, over any
specialist in its `workers` list; each unit names its `agent`, effect and tier. A single finished unit is returned
as the reply with no assembly completion; chains are assembled from the results. Add a specialist to `workers`
to make it reachable from Ember.

The other task-shaped kinds share the `task` plan format and add one rule each, checked when the plan is parsed:
`review` (answering units, one per part of the question, checked by a reviewer unit that depends on them and cites sources),
`writing` (one outline unit, then sections that depend only on it) and `operations` (reads first; every write depends on a
read and is followed by a read that verifies it; the reply lists changes and how to undo them). Chains of every kind except
`writing` flag a figure in the reply that no specialist result contains. There is still no approval step for writes.
The tool-free `writer` specialist (port 29623) drafts prose for `writing` and `review`.

`mathematician` (port 29620) handles standalone mathematical questions through
Armory's `tool_math_*` tools: equations, units, matrices, calculus, and repeated
formulas. Its answers retain verification, completeness, assumptions and domain
conditions. It does not replace unavailable tools with manual computations.
Enable Armory's Mathematics capability for this specialist to be usable.
The existing roster filters hide it when its math tools are unavailable.

Ember routes standalone mathematics to Mathematician and attached-table work to
Analyst, using only the current available roster. Analyst can use math tools for
derived formulas over owned numeric table pages; it retains table discovery and
token-usage tools. Reviewer already permits math tools and now receives explicit
instructions for independent mathematical checks from the original problem.
Ember retains its existing tool scope and delegates calculations.

These are tracked defaults. Per-machine agent overrides can shadow them; update
or clear those overrides in the admin UI if present. The supervisor watches agent
definitions and reconciles validated changes; an unchanged running deployment
needs the updated files and Armory workers before the new capability is usable.

`server-ops` also covers app monitoring (the former `scheduler` / App Monitor agent, port 9114, now removed). It reports
watched status, and starting an app also starts its owner notifications through ServerWatcher. URL/port monitoring and
recurring schedules are unavailable. `data-analyst` (label "Analyst") also answers token-usage questions through
`stronghold__tool_usage_summary` (the former `usage-analyst`, port 9108). The `planner` agent is retired: Ember plans with its own
`update_plan` tool. An `agent:scheduler`, `agent:planner` or `agent:usage-analyst` entry in a user's saved agent switches no longer matches
any agent. Restart the supervisor to load the updated definitions.

The gateway for an agent comes from `llm.gateway` in `agents/<id>.json`.
Omitted, it is the provider's default gateway (`claude` for anthropic, `gpt`
for openai). Provider, gateway and model are never set in `.env`. There is no
`--gateway` flag; saved launcher presets that pass one have no effect.

Exactly one enabled file must set `entry: true`. The supervisor validates
every file before it starts anything and refuses to start, naming the file
and field, on a bad file, a shared port among enabled agents, or a wrong
number of entry agents.

`python -m src.supervisor` starts all agents: it
spawns one `python -m src.server` child per enabled file (env
`AI_AGENT_FILE`), prefixes each child's output with `[<agent id>] `, and
restarts a crashed child with backoff (1s, 2s, 4s... capped at 60s; left
stopped after 5 crashes within 5 minutes, the others keep running).

To run one agent alone, set `AI_AGENT_FILE` to its file and run
`python -m src.server`.

## Upgrading from Garrison

`git` moves only tracked files when `apps/garrison` becomes `apps/legion`. Copy the untracked
local state yourself, with the services stopped:

```powershell
Copy-Item apps\garrison\.env apps\legion\.env
Copy-Item -Recurse apps\garrison\.data apps\legion\.data
Copy-Item apps\garrison\configs\config_*.json apps\legion\configs\
```

Then recreate the virtual environment with `uv sync` (see Setup) and point any local
`portcullis` `config_app.json` `agents_registry_path` at `../../legion/.data/agent_registry.json`.
Stored agent overrides in `.data/agent_overrides.json` that still use `orchestrator` or
`internal_role` are upgraded to `role` when loaded.

## Running on another machine

portcullis finds agents through the registry. On the same machine it reads
`.data/agent_registry.json`; from another machine it fetches `GET /registry`
(served by every instance, same JSON, authenticated by signed service assertions like
`/mcp`). Both also carry `defined`: every agent in `agents/`, running or not
(the supervisor writes `.data/agent_definitions.json` at start), so the Agents
page can show an agent that is stopped or disabled. On the ai_agent machine:

- `AI_AGENT_HOST=0.0.0.0` so it accepts outside connections.
- `AI_AGENT_ADVERTISE_URL=http://10.0.0.5` (an address peers can reach, no
  path). This is the address registered for each agent; without it a bind-all
  host registers as `127.0.0.1`. Leave the port out when the supervisor starts
  several agents: each one adds its own port. A value with a port is used as
  is (single instance).
- Mount the shared public trust folders and Legion's own private identity folder,
  and open the ports in the firewall. Use a private network or TLS.

Then set `agents_registry_url` in `apps/portcullis/configs/config_app.json` (see
`apps/portcullis/configs/README.md`).

## Decision question agents

Agents with `llm.provider: "decision"` answer typed JSON questions without tools or
text generation. Their `llm.strategy` is `laya-only`, `jev-only` or `both` (default),
and their `llm.min_confidence` is unset by default, so each gateway uses its own
thresholds: Laya per model and option count (English 0.90 / typed 0.80 for two options,
0.75 / 0.55 for three or more), Jev 0.90. A number sets one bar for every gateway. With `both`, Laya answers first;
Jev receives only questions that Laya fails to settle. `local_only: true` forces
Laya only. An uncertain last answer stays marked `uncertain`. A later gateway's answer
replaces an earlier one only when it settles the question or is at least as confident.
Without `"trace": true` the answers leave out the service's `rounds`, `voters` and
`options` detail.

Confidence scales differ on purpose: agents and the router use a fraction (above 0, up to 1,
unset by default); `classifier.auto_tier` and `classifier.auto_route` use a whole percentage
(1 to 100). Zero is refused because the Laya service needs a value above zero. A router
takes its `strategy` and `min_confidence` from `llm` unless its `decision` block sets them.

Send `{"text": "...", "questions": {...}}`. Each question has a `type`, optional
`instructions`, and `criteria`: a map of options for `choice`, an ordered list of
levels for `score`, or false/true labels for `noul` (yes/no). Requests may override
`min_confidence`. The wrapper accepts up to 16,000 characters; Laya's own window
is 4,000, so longer requests need Jev or return unavailable with `laya-only`.

Laya runs in the separate LayaModel service, reached through DecisionGateway. Its internal
strategy is set on the `laya` gateway entry there (`english-then-typed` by default). Callers and
account settings do not choose a Laya service strategy. Jev's model and key are set on the `jev`
entry; cloud requests send text off this machine.

Answers contain per-question confidences, uncertainty and the gateway that
answered. Confidence scores are not calibrated accuracy claims. Token usage
reports actual input work and zero generated output tokens.

Run `python -m scripts.check_router_cases --offline` for synthetic contract
checks. Live diagnostics require a prepared deployment:
`python -m scripts.check_laya_triage` uses only Laya, and
`python -m scripts.check_triage_cases` supports `--list`, `--case NAME`,
`--strategy both|laya-only|jev-only`, `--baseline` (Laya only), `--rounds` and
`--json`. These are smoke examples, not accuracy benchmarks.

## Orchestrator

The orchestrator always plans: it is offered only `ask_user` and `submit_plan`, never direct tools or `delegate_to_agent`, and its plan runs through the architects in its catalog.
The roster text below describes specialists that other agents may call. Each turn the orchestrator's roster is built from the
registry: eligible registered specialists (never the agent itself or an internal Router), as lines of `<id> - <label>: <focus>`. Because it is per turn,
a specialist that starts or stops shows up without a restart. A specialist with
tools of its own (`tools.allow`, apart from the ticket tools) is left out when
none of them is offered right now: its capability is switched off on mcp_server,
or the asking user switched the specialist off (`agent:<id>` in `disabled_tools`). A specialist with
no tools of its own always stays. If mcp_server's tool list cannot be read, or is
empty, nobody is left out. The
`agent_id` argument of `delegate_to_agent` is an enum of the roster ids. An
orchestrator may still answer directly when no specialist fits.

Tool calls of one model round (`src/runtime/tool_batch.py`, shared by the Anthropic and OpenAI
loops): consecutive calls run at the same time (at most `tool_batch.max_parallel`, 8 by default) only when each needs no approval and is a
built-in tool that declares `readOnlyHint`. Any other call (a write, a delegation, a local tool such as
`update_plan`, a private tool, one that needs approval) runs alone and in order, so approvals are asked
one by one. Results go back to the model in the model's call order. The turn guard checks every call of the
round before the first one runs.

These limits are settings in Legion's settings database (table `tuning` in `settings.db`, like every other Tuning edit), edited on the
Tuning page of the admin app under "Tool calls" (`tuning.manage`), and read again at the next round of calls.
They are saved through `PUT /agents/tuning` with the paths below; no config file or environment variable holds
them. A missing row means the default.

| Path | Default | Range | Meaning |
|---|---|---|---|
| `tool_batch.parallel` | on | on/off | Off runs every call one at a time. |
| `tool_batch.max_parallel` | 8 | 1-16 | Most calls that overlap. |
| `tool_batch.batch_tool` | on | on/off | Offer `run_tools` to specialists. |
| `tool_batch.max_steps` | 10 | 2-20 | Most steps in one `run_tools` call. |
| `tool_batch.max_result_chars` | 20,000 | 1,000-100,000 | Longest result returned for one step. |
| `tool_batch.max_total_chars` | 60,000 | 5,000-200,000 | Longest reply for one batch. |

A specialist with more than one real tool is also offered `run_tools` (`src/runtime/run_tools.py`): one
step that holds up to `tool_batch.max_steps` tool calls `{id, tool, arguments, return?}`. Steps with no link between them run
in the same wave under the rule above; an argument `{"$ref": "id"}` (whole result) or
`{"$ref": "id.field.0"}` (a field of a JSON result) makes a step wait for that step. The model gets one reply:
steps with `"return": true`, and by default the steps nothing else uses, come back in full (cut at the
limits below); the others show a status line and their result stays available to later
`$ref`s of the same turn. A failed or declined step makes only the steps that need it skip. Every step is an
ordinary call, so the turn guard, approvals (asked step by step), tool filters and error numbers apply to it.
A step may not call `delegate_to_agent`, `ask_user`, the plan tools or `run_tools`. The orchestrator, architects
and the router are not offered it.

With `mode: "plan"`, the model sees only `ask_user` (when the caller supports
questions) and `submit_plan`. The catalog is rebuilt from the live registry,
capped at 8,192 characters; worker lines are dropped before architect lines.
Only architects included in that snapshot may be named by a plan. A submission
has 1–8 steps, unique ids, known dependencies, no cycles and self-contained
briefs of 20–16,000 characters. The first rejection returns the exact validation
error for one repair; a second rejection asks for a direct answer. Accepted
plans execute through the shared DAG executor, then the model receives the
results with no tools offered and writes the final reply. Architect-level code
steps are read and may retry; operations and unknown kinds remain write. Unit-level read retries
escalate light to standard to heavy; writes are never retried automatically.

Automatic memory and skill searches still run before the model. Skill recall
omits its `stronghold__tool_skill_mark` instruction for the orchestrator; the runtime does not
mark skills. The runtime fills the existing checklist when its agent/chat
toggles allow it. The router is asked first, also for the orchestrator: a settled pick sends the turn straight to that
specialist and Ember's planner does not run; an unsure or failed Router leaves Ember to plan, with the model tier the router chose. The code architect ships enabled and Ember plans through it.
Operations has no pipeline yet.

Specialist activity streams to the orchestrator's caller as `agent_start`,
`agent_end` and `agent_token` events, and a specialist's own `step_*`
events pass through stamped with its `agent_id`. A specialist's step ids can
collide with the orchestrator's, so consumers key on `(agent_id, id)`.

## Architects

`agents/code-architect.json` defines the code pipeline, using OmniRoute's
`combo/heavy` for planning and assembly. It is disabled by default and has no
model-offered tools. Enabling it does not switch Ember to plan mode.

The pipeline optionally calls the first configured prefetch specialist when the
brief names a code file or conservative path, caps its output at 8,000 characters,
and continues on prefetch failure. One tool-free completion plans a bounded DAG
of functions or methods, fixing signatures and dependency contracts. A rejected
JSON plan gets one repair with the exact validation error; a second rejection
fails the architect call. The kind registry selects the handler; code prompts
and validation live separately from the shared pipeline.

Workers use `workers[0]`; decision-router selection is deferred. A unit receives
its own signature and every dependency's signature, plus finished bodies only
for `needs_body_of`. All code units are read-only text generation. Python unit
outputs must parse with `ast`, with retries and tier escalation under the
architect's limits. Other languages rely on the assembly review.

Assembly receives the brief, plan, outputs and every missing unit. It must check
calls against planned signatures or definitions in pasted code, flag possible
invented APIs and state incomplete work. Python also receives a final syntax
check and a conservative call-contract audit. No generated code is executed.
Each planner, repair and assembler completion has its own durable usage row;
worker usage is retained through the normal delegation path. Cancellation is
cooperative, and an already-running one-shot completion may finish upstream.

Operations, approvals, runtime skill marking and the Ember rollout remain deferred.

## Trusted gateways and confidential data

Each model gateway has a **Trusted** switch on its setup (Model gateways page, chat and decision lists). A gateway
without a saved choice defaults by what it is: the hosted models `claude`, `gpt`, `gemini` and Jev, and every gateway
that runs on this machine (Ollama, the Scuti model services, Laya). Others, such as OmniRoute, OpenRouter,
FreeLLMAPI, Bedrock and Vertex, start untrusted until an admin marks them. Code: `src/gateway/trust.py`.

- **Every agent keeps one trusted gateway.** Saving an enabled agent whose gateways (`llm.gateway` and
  `llm.fallback_gateways`) are all untrusted is refused (409). Untrusting or deleting a gateway that is the only trusted
  one of an enabled agent is refused too, naming the agents. Decision agents have no chat gateway and are not checked.
- **Confidential data goes only to trusted gateways.** The `confidentiality-checker` agent
  (`agents/confidentiality-checker.json`, decision provider, strategy `jev-only`) says whether text holds credentials,
  personal identifiers, bank or card numbers, health, legal or financial details, or private messages and documents
  (`src/runtime/confidentiality.py`). The check runs at the start of a turn, and again on each round of tool results,
  only while the agent has an untrusted gateway to protect from. A confidential turn moves to the first trusted
  gateway of the agent (the step list shows a gateway switch with reason `confidential`) and stays on trusted ones:
  failover never picks an untrusted gateway. Delegated agents inherit the mark (`ask(confidential=true)`).
- **It fails closed.** A checker that is missing, disabled, unreachable, slow or unsure counts as confidential. When
  no trusted gateway can take a confidential turn (credentials missing, in cooldown), the turn ends with an error and
  nothing is sent to an untrusted one.
- **Marked without a check:** a turn that recalls memory notes or skills, or carries the user's own MCP servers
  (private extensions), is confidential at once when the agent has an untrusted gateway, because those are the
  user's own data. A confidential turn also skips untrusted decision gateways (Laya, Jev) for the Router and other
  decision agents, and ends with an error when none is left.
- **Not covered:** text that only appears after the last tool result of a turn; the check reads at most 4,000
  characters (start and end) of what it is given. FreeLLMAPI's decision gateway is listed on the page but no strategy
  asks it.

## Gateway health

A failed gateway call starts a cooldown (`gateway_failover` in Tuning sets how long). Cooldowns and the last 50
failures per gateway are kept in `settings.db` (tables `cooldowns` and `gateway_health`), so every agent process and a
restart see them; a process re-reads them every 2 seconds, and an unreadable database never stops a turn. The chat list
on the Model gateways page shows each gateway as cooling down (with the time left), its failures in 24 hours, or healthy.


## Internal Router agent

`agents/router.json` defines the supervised internal Router on port 29616. It is
visible on both Agents pages, but cannot receive chat questions or appear in a
delegation roster. Ember Admin's existing Agents editor (`agents.manage`) controls
its enabled state, task switches, local voters, confidence thresholds, narrowing,
deadline, remote timeout, tier mapping and optional trace. Saves use the existing
machine-specific override and supervisor restart; Reset restores tracked defaults.

For a top-level entry/orchestrator turn with conversation history, Legion first
asks the tool-free `context-summarizer` for a short routing brief. Router receives
that brief, the latest user message verbatim, and the authorized specialist roster.
If the helper is unavailable, times out, or returns an unusable brief, routing uses
up to 600 characters of the previous assistant message instead. First messages
need no summary call. Memory injection and full history are excluded from Router.
The tracked `router.json` uses strategy `jev-only`, so the routing brief and the latest
user message go to TypeSafe on every routed turn; set `llm.strategy` back to `both` or
`laya-only` (through the Agents editor or the file) to keep routing text on this machine. It returns
independent agent and size decisions.
An uncertain agent choice stays with Ember; uncertain size uses the selected
agent's default model. Explicit tiers and target limits still apply. Delegation
requiring approval remains Ember's responsibility.

The Router requires a configured shared internal token even for local use. Its
operation is not available through the browser MCP proxy or the assistant's tool
catalog. It has no tools, private extensions, memory recall or plan capability.
Internal role invariants are validated on file/Admin changes and at startup.

Router's local voters are the Laya service's too. To make sure Router never triggers a weight download, run the
service with `LAYA_OFFLINE=1`: it then loads only checkpoints that are already cached completely, and preparing
them stays an operator action. Ordinary chat abstains from unavailable local voters and can use the configured Jev
fallback. Readiness summaries report `local_status` `loaded` when the service answers its health check and
`unavailable` when it is missing or unreachable, and flag missing fallback credentials.

Defaults: 10-second overall deadline (1-30 configurable), 3-second remote timeout,
4,000 local subject characters and 16,000 remote subject characters. Inputs are not
silently truncated to fit.

One agent question carries at most nine specialists plus `none`. A longer roster is
narrowed in rounds (`RouterEngine._narrow`): the candidates are split into the fewest
batches of equal size (sizes differ by at most one) and each batch is asked in parallel
with its own `none` option. A batch whose pick is `none` drops out whole. Otherwise it
keeps every option whose probability is at least a quarter of its pick's. The survivors
are pooled and, while more than nine remain, split and asked again; a round that prunes
nothing keeps only each batch's pick, so rounds always shrink. The last round asks the
survivors (at most nine) plus `none`, and the highest wins if settled. If every batch
picked `none`, the agent choice stays with Ember (`no_specialist`). The size question runs
alongside the first round. Pruning needs per-option probabilities; a gateway that reports
only the pick's confidence gets an even split of the rest, which prunes little. Rounds share
the overall deadline, so a timeout falls back to Ember.

When the final round settles on an agent and a runner-up has at least 80% of the winner's
probability, the response lists it in `alternatives`. The winner still receives the
question; the routing step reads "Also close: ..." and the Router usage row carries the ids. Short
follow-ups with history skip tier selection unless the summarizer supplies context.
Tier mapping is tiny/everyday to
light, large to standard, hardest to heavy. Thresholds remain the triage defaults,
not an accuracy guarantee. Missing/offline/disabled/failed Router uses normal
Ember orchestration and default tiers; legacy direct Jev routing does not restart.

Router usage is attributed to `router`, per actual voter/backend/model attempt,
without an entry-model row when no entry model ran. Optional diagnostics retain
settled/uncertain outcomes and bounded trace metadata without copying user text.
Late inference cannot dispatch work; actual late completions remain in Router's
local usage log. Browser APIs keep their existing usage and log permissions.

### Shared context summarizer

`agents/context-summarizer.json` defines the supervised helper on port 29617.
It uses the existing Anthropic/OpenRouter light tier (currently `openrouter/free`
in tracked defaults), with no tools, delegation, memory recall or planning. It
is not an entry agent or a routable specialist. The existing agent editor and
deployment override mechanism control its model, enabled state and limits.

The `interpret` operation accepts two caller prompt modes: `routing` produces
a factual brief without selecting an agent or tier; `compact` preserves the
continuation context, decisions, pending work and exact identifiers. Routing
waits at most five seconds, accepts at most 1,600 summary characters, and bounds
history to about 32,000 characters while retaining the start and recent turns.
The prompt discloses omitted middle history. Existing compacted history is input
like other messages; no additional per-chat summary store is introduced.

Routing summaries are recorded as `context-summarizer` work in the turn's usage
breakdown, separately from Router voters and answer generation. Cancellation or
timeout discards late results; a tool-free `interpret` inference already running
on the remote service may finish after the caller stops waiting.
Completed `interpret` calls write the helper's local usage log before returning,
including late completions after a timeout. Late usage cannot be attached to an
already completed Ember turn; the helper log retains it with the routing request
ID for reconciliation. Regular successful calls appear once in account usage.

Ember API also discovers this helper for `/compact` and automatic compaction.
Those calls keep the existing full compaction prompt, transcript backup,
recompression and summary usage accounting. They do not use the short routing
brief as the chat's replacement memory. No helper means manual compaction
reports unavailability; automatic compaction keeps the history and continues.

### Decision gateway configuration

The `classifier` tuning section contains `timeout_seconds`, `max_input_chars`,
and the `auto_tier` / `auto_route` helper settings (`enabled`, `strategy`,
`min_confidence`; auto tier also has a size-to-tier mapping). Strategy values are
`laya-only`, `jev-only`, and `both`; these helper confidence thresholds use
percentages from 0 to 100. Admin Tuning edits strategy and confidence; enable
flags and tier mappings stay in the file. Router uses its agent's separate
`decision` policy and does not mutate these helper settings.

Laya and Jev connections and model presets are saved in DecisionGateway under the ids `laya`
and `jev`; `gateways/decision/` keeps only their labels.

## Usage log

Every completed `ask` appends one JSON line to
`.data/usage/YYYY-MM-DD.<agent id>.jsonl` (UTC date; one file per agent per
day, so no two processes write the same file). Each line is the `agent_usage`
row the `ask` result carries, plus `request_id` and `depth`:

- `agent_id`, `agent_label`
- `provider_id`, `gateway` (`null` when the provider is used directly), `model`
- `input_tokens`, `output_tokens`, `total_tokens`
- `started_at`, `finished_at` (UTC ISO-8601 with milliseconds)
- `prompt` is added to the row the `ask` result returns, not to the file: the history and question this agent received as `{role, content}` messages (`core/usage_log.prompt_messages`). A delegate's row therefore carries the question its orchestrator sent. The system prompt is never included. portcullis stores it for the Advanced chat-turn view.
- `delegated_by` (`null` for the top-level agent)
- `request_id`, `depth`

Set `AI_AGENT_USAGE_DIR` to write somewhere else. A cancelled turn writes no
line; only completed asks do. A write failure logs a warning and never fails
the turn. `.data/usage/` is gitignored.

## Tools and agents the user switched off

`ask` also takes `disabled_tools`: `agent:<id>` entries for specialists the asking user switched
off for their own chats (the roster leaves them out and `delegate_to_agent` refuses them), plus mcp_server tool names (`src/runtime/tool_filter.py`). For that turn the agent does
not offer them (`list_tools`) and refuses a call to one the model names anyway.
A delegated agent is told the same list. `status()` reports `tool_filter: true`
so portcullis can refuse an agent that would ignore the option.
`disabled_tools: ["*"]` blocks every built-in, shared-extension, and private-extension
tool when the Ember account lacks `tools.execute`.
A name that starts with `!` is an exception: `["*", "!stronghold__tool_brain_search"]` blocks everything except that one tool, for the model's own calls and for Legion's memory recall alike. An exception for a tool that is not blocked changes nothing, and a delegate gets the same list. Portcullis uses it for outside clients at the Stronghold level (five Brain tools). `status()` also reports
`tool_filter_all: true`; portcullis and delegates refuse older agents without it
before starting a restricted turn. The filter follows nested delegation.

`ask` also accepts `private_extensions`, the user's own MCP servers for this
turn; see the next section for its shape and behavior.

## Outside MCP connections

Legion Admin accepts an MCP address and uses Treasury to find or register its outside service.
A saved HTTP entry holds `service_id`, a shared `path` (default `/mcp`), and an ordered
`origins` list of `{origin_id, header_value?}`. Legion uses the entry's `auth` header
as the connection token. An origin can override its header value. Stored tokens are write-only.

Legion tries the listed origins in order. A connection failure or timeout puts the origin
on a 30-second cooldown. A tool call that fails returns its error. The next call uses the
backup when one is available. The MCP registry's tool listing checks whether a preferred origin has recovered
after the cooldown. A protocol or HTTP refusal does not trigger failover.

A tool from an outside MCP connection uses the name `<server-id>__<tool>`.
Add a matching `tools.allow` glob such as `bard__*` to offer it to the agent.
An empty allow list leaves outside connection tools hidden, and `tools.deny` still wins.
Outside tools follow the normal approval policy, including in Auto mode.

Edits apply the next time Legion starts. Armory's `main` connection still uses a `url` entry.

### Stronghold MCP connection

The built-in `stronghold` connection discovers Stronghold's `/mcp` address through
Treasury. A saved server with the ID `stronghold` overrides the built-in address. Citadel
credentials go only to the Stronghold address registered in Treasury.
Legion starts without Stronghold and retries the connection in the background.

Agents need `tools.allow: ["stronghold__*"]` or a matching individual tool entry
to see and use stack tools. Stronghold supplies the optional `chat_id` argument
of `ask`. Legion forwards it with the signed requester as Stronghold MCP call
metadata so the tools can select the requester's chat.

## Private extensions

A private extension is a user's own MCP server, passed to `ask()` per turn by
portcullis. Its tools belong to that account and turn only. Private extensions
are never forwarded to delegated agents.

The `private_extensions` argument is `[{id, label, url, headers}]`; `headers`
is an optional object of header names and values, and `label` defaults to `id`.
Validation applies before connecting:

- `id`: at most 40 characters, matching `^[a-z0-9]+(_[a-z0-9]+)*$` (no `__`).
- `label`: trimmed to 60 characters.
- `url`: at most 1000 characters, `http` or `https`, with a host and no
  username or password in the authority.
- `headers`: at most 20; names match `^[A-Za-z0-9-]{1,64}$`, values are 1–2000
  characters with no control characters. Connection-controlling headers are
  refused, case-insensitively: `host`, `content-length`, `transfer-encoding`,
  `connection`, `upgrade`, `te`, `trailer`, `proxy-authorization`, and `cookie`.
- At most 100 tools per extension. Full tool names must be at most 64
  characters and match `^[A-Za-z0-9_-]+$`; others are left out with a notice.

Public and private LAN addresses (`10/8`, `172.16/12`, `192.168/16`,
`fc00::/7`) are allowed. Loopback, link-local, unspecified, multicast,
reserved, `0.0.0.0/8`, `64:ff9b::/96`, and cloud metadata addresses
(`169.254.169.254`, `fd00:ec2::254`, `100.100.100.200`) are blocked, including
IPv4-mapped IPv6 forms. If any resolved address is blocked, the host is
refused. The guard checks every connection and redirect and pins the
connection to a checked IP, keeping the original Host header and TLS server
name, so a second DNS answer cannot redirect it. Redirects are followed only
to the same scheme, host and port, at most three hops; configured headers
therefore never follow to another host.

Tools are named `u_<id>__<tool>` and honor the agent file's `tools` scope.
They always ask before running, even with `approval_mode="off"`, unless
already in `allowed_tools`. An `always` decision allows the tool for the
rest of the turn; mode `deny` refuses tools that need approval.

A private tool's result is text from a server this agent does not control, so
once one has run in a turn (whether it succeeded or failed) every later tool in
that turn asks first as well, unless the user already allowed it for the chat.
A result longer than 50,000 characters is cut, with a note saying so.

An unavailable extension does not fail the turn: its tools are omitted and
`ask()` includes `private_extension_errors: [{id, label, error}]` in the
reply when there are errors. Header values are hidden in error messages.

The `probe_extension(url, headers=None)` MCP tool connects once, lists tools,
and closes, returning `{status, error, tools}`. A bad server returns
`status: "error"` and an empty tool list instead of raising.

`status()` reports `private_extensions: true` for supported providers, so
portcullis can refuse an older agent that would ignore the argument. Laya
agents report `false`: they use no tools and do not support
private extensions.

## Asking before tools run

`ask` takes `approval_mode` and `allowed_tools` (`src/runtime/approvals.py`):

- `off` (default): tools run as before. chat_app never sets a mode.
- `ask`: before each tool that is not in `allowed_tools`, the agent emits an
  `approval_request` event (tool, label, arguments) and waits. The tool runs only
  after the `decide(request_id, step_id, decision)` tool answers `allow` or
  `always` (also stop asking about that tool for the rest of the turn). `deny`,
  no answer within 4 minutes, or a Stop all mean it does not run, and the model
  is told so in place of a result. `delegate_to_agent` asks like any tool.
- `deny`: a tool that would need asking is refused at once. A delegated agent
  gets this from a turn that asks, since it cannot reach the user.

`ask(allow_read_only=True)` with `approval_mode="ask"` is "Auto": a built-in mcp_server tool
that declares `readOnlyHint` (its `main__<tool>` name, no extension id) runs without asking.
Everything else still asks: tools with no declaration, an extension's tools (they could vouch
for themselves), private extension tools, and every tool once a private tool has run in the
turn. A delegated agent (`deny`) still cannot run a tool that would need asking. The tool
names come from the last `list_tools()` (`mcp_upstream.is_read_only_builtin`). `status`
reports `read_only_approval: true`.

`status` reports `tool_approval: true`, so a caller that needs tools asked about
(portcullis) can refuse an older agent that would ignore the option.

`ask(ask_user=True)` offers the top-level agent clickable questions; answer or
skip through `answer_question(request_id, step_id, answers, skipped)`. Questions
emit `question_request` / `question_resolved`, wait up to 60 minutes with
keepalive events, and Stop cancels the turn. `status()` reports `user_questions: true`.

`ask(plan=False)` withholds the `update_plan` checklist tool for a turn, and `ask(plan_lean=False)` drops the instruction to update it only when an item changes status (with it on, an unchanged list is also skipped without an event). Both default on and are sent to specialists too; `status()` reports `plan_toggle: true`.

`ask(exact_context=True)` counts what fills the context window with the provider's own token counter (`src/providers/context_breakdown.py`; Anthropic `count_tokens`, OpenAI `responses.input_tokens`) instead of estimating it at about four characters a token. The result's `context_breakdown` lists the parts (system prompt, delegable agents, built-in tools, MCP tools, messages) and `context_breakdown_exact` says whether the provider counted them. Counts are cached by model and content, so only the first turn after a change to the prompt, the tools or the model makes requests; any failure or a 3 second wait falls back to the estimate, so counting never fails a turn. `status()` reports `exact_context: true`.

## Prompts

Each agent's system prompt comes from its own `agents/<id>.json`, in this order:

1. An identity line, `Your name is Ember: <role>`. The role is `Orchestrator`
   for an orchestrator, else the file's `label` (`Ember: Researcher`,
   `Ember: Reviewer`).
2. `persona`.
3. For an orchestrator, the roster of specialists, rebuilt each turn.
4. `instructions`. Empty uses `DEFAULT_INSTRUCTIONS` in `src/agents/agent_roles.py`.

Shared defaults live in `configs/config_prompts.json`; agent files supply their
own persona and instructions. The supervisor watches both definitions and shared
prompts, restarting affected children after validated edits. The admin Shared
prompts editor confirms changes that restart every agent.

Agent files give each instance its own id, so any number of same-provider agents can run side by side.

## Security

- **Service authentication is mandatory**: Ed25519 assertions authorize every
  backend request; only `/health` is exempt. Private identity stays outside public trust.
- **Requester identity is signed by Portcullis**: each MCP tool call verifies
  `_meta.requester_token`; delegated calls forward that token. Verified renewal
  updates reach running asks, and expired requester tokens cannot be forwarded.

## Project layout

- **`agents/*.json`** - tracked default agent definitions; admin UI changes go
  to the untracked `.data/agent_overrides.json` instead. See [`agents/README.md`](agents/README.md).
- **`gateways/<provider>/*.json`** - tracked individual gateway presets,
  read directly. See [`gateways/README.md`](gateways/README.md).
- **`configs/*.json`** - structured settings, mostly gitignored. See
  [`configs/README.md`](configs/README.md).
- **`.env`** - the one credentials file (provider, gateway, role, API
  keys), gitignored; copy it from `.env.example`.

See [`src/README.md`](src/README.md) for the full code map - what lives
where, and where new code goes.

See
[`docs/superpowers/specs/2026-09-07-ai-agent-mcp-layer-design.md`](../docs/superpowers/specs/2026-09-07-ai-agent-mcp-layer-design.md)
for the full design rationale.

Treasury bootstrap address lives in tracked `configs/config_app.json` as `treasury_url`; `TREASURY_URL` overrides it. Legion entry agents register their base address in Treasury’s catalog. Treasury Admin, Services controls address pins; Legion Admin no longer edits Treasury’s address.

## Liveness, readiness, and tool failures

`GET /health` is public and answers `{"status":"ok"}` while the process runs.
`GET /ready` requires a signed Citadel service assertion. Authorized calls return
HTTP 200 with dependency addresses and states (`configured`, `reachable`,
`unreachable`, `not_configured`) even during an outage.

| Code | Failure | Retryable |
|---|---|---|
| 1000 | `TOOL_INTERNAL` | No |
| 1001 | `DEP_NOT_CONFIGURED` | No |
| 1002 | `DEP_UNAVAILABLE` | Yes |
| 1003 | `DEP_TIMEOUT` | Yes |
| 1004 | `DEP_AUTH_REJECTED` | No |
| 1005 | `DEP_ERROR` | Maybe |

Legion stops a repeated call with the same arguments when its previous failure was non-retryable.
