# ai_agent

A standalone MCP agent, hard-pinned to one LLM provider+model, sitting
between `chat_app` and `mcp_server`:

```
chat_app  --(MCP: ask/interpret/status/cancel/decide)-->  ai_agent  --(MCP, persistent)-->  mcp_server
```

It is both an MCP *server* (to `chat_app`, exposing
`ask`/`interpret`/`status`/`cancel`/`decide`)
and an MCP *client* (to `mcp_server`, via a persistent connection - see
`src/mcp_client/mcp_upstream.py`). Run one agent per provider (see Agents) to back
`chat_app`'s Claude Agent / OpenAI Agent dropdown entries.

## Setup

1. Copy `.env.example` to `.env` and
   fill in `CLAUDE_API_KEY` and/or `GPT_API_KEY` (whichever provider(s)
   you're running), or the key(s) for whichever `llm.gateway` your agent
   files point at instead. Both can be set at once - one file backs every agent.

2. Make sure `mcp_server` is running (`py -m src.run` in `apps/armory/`) -
   `apps/garrison/configs/config_servers.json` points at its default
   `http://127.0.0.1:8010/mcp`.

3. Start the agents from `apps/garrison/`: create `.venv_garrison` and install the
   project once (`py -m venv .venv_garrison`, then `.venv_garrison\Scripts\pip install -e ".[dev]"`),
   then run `.venv_garrison\Scripts\python -m src.supervisor`. See Agents below.

### Laya models

Garrison does not install Laya, PyTorch or the model weights, and no Garrison code loads a Laya model.
Both models and every local decision rule live in the shared Laya service (`Python/LayaAgent`, behind a
load balancer); Garrison reaches it over HTTP through one client, `LAYAAgent` (`src/llm/laya_agent.py`).
Set `LAYA_SERVICE_URL` (the root `docker-compose.yml` sets it to `http://laya_lb:9120`) and `LAYA_TOKEN` if the
service has one. Start the Citadel stack first (it creates the `citadel_core` network), then the service
(`docker compose up -d --build` in `LayaAgent/`); Garrison finds it by name when it first needs it. Without `LAYA_SERVICE_URL` no Laya model is available: the Triage Assistant, the Router's
local voters and the `laya` classifier backend report that, and Jev (where allowed) answers alone.
For local development run the service (`run.bat` in `LayaAgent/`) and set `LAYA_SERVICE_URL=http://127.0.0.1:9120`
in `apps/garrison/.env`.

Garrison sends the service a strategy name per question type and gets the answers back; what stays in Garrison is
the cloud fallback (Jev) and its use. See [Triage flow](#triage-flow-laya-english-laya-typed-decisions-jev).

An older image keeps its GPU packages until it is replaced. From the repo root,
rebuild and recreate Garrison (`dev_deploy.bat` in this folder does the same on a dev machine). On the ZimaOS box
`COMPOSE_FILE` in the root `.env` already selects the overlay, so no `-f` flags are needed:

```sh
docker compose build garrison
docker compose up -d --no-deps garrison
```

## Agents

Each ai_agent instance is defined by one file, `agents/<id>.json`. The file
name stem is the agent id (`^[a-z0-9][a-z0-9-]{0,62}$`). `agents/` is
tracked in Git, including edits made through the admin UI. Create or copy an
agent file and edit it directly. Unknown keys are an error, so
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
  "port": 9103,
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
  "orchestrator": false
}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `label` | no | id | Display name. |
| `port` | yes | none | Port the child listens on. Unique across enabled files. |
| `enabled` | no | `true` | `false`: not spawned, not registered. |
| `entry` | no | `false` | The agent ember sends new turns to (Phase 2). Exactly one enabled file must set it. |
| `llm.provider` | yes | none | `anthropic`, `openai`, or `laya` (local typed questions only). |
| `llm.gateway` | no | provider default | A filename stem from `gateways/<provider>/<gateway>.json`. |
| `llm.fallback_gateways` | no | `[]` | Ordered same-provider backup gateways, as names or `{gateway, model?}` objects. See Gateway failover below. |
| `llm.model` | no | gateway's `model` | Model id. |
| `llm.temperature` | no | unset (provider default) | Float 0-2. |
| `llm.reasoning_effort` | no | `off` | `off`, `low`, `medium`, `high`. Maps to the Anthropic thinking budget or OpenAI `reasoning_effort`. |
| `llm.max_tokens` | no | today's hard-coded value | Output token cap per model call. |
| `llm.max_tool_rounds` | no | `6` | Cap on the tool loop. |
| `persona` | no | `""` | Persona text placed after the identity line in the system prompt. |
| `instructions` | no | `""` (built-in default) | Tool-use instructions placed last in the system prompt. Empty uses `DEFAULT_INSTRUCTIONS` in `src/llm/agent_roles.py`. |
| `focus` | no | `""` | One-line summary of what the agent is good at. Used for the orchestrator roster. Should be concrete. |
| `tools.allow` | no | `[]` (all) | fnmatch globs on mcp_server tool names without the `main__` prefix. Empty means all tools. |
| `tools.deny` | no | `[]` | Globs removed after `allow`. Deny wins. |
| `orchestrator` | no | `false` | Gets `delegate_to_agent` and the roster. |
| `memory_recall` | no | `false` | At the start of each top-level turn, load the user's newest saved notes (`tool_mem_search`, up to 10) and put them in front of the question. Needs the `memory` capability online and an agent that may call `tool_mem_*`. Not allowed for Laya. Only `ember` has it on. |
| `skill_recall` | no | `false` | At the start of each top-level turn, search the user's **approved** skills with the question (`tool_skill_search`, up to 3) and put the matches in front of it, after any recalled notes. A proposal never loads before the user approves it on Ember's Skills page. Needs the armory `skills` capability online and an agent that may call `tool_skill_*`. Not allowed for Laya. Only `ember` has it on. |
| `skill_learning` | no | `false` | After a top-level turn that made at least 3 real tool calls and none failed, draft a reusable skill in the background and propose it (`tool_skill_propose`) for the user's approval. One extra call to the tool-free `context-summarizer` agent per qualifying turn, so it is billed: switch it on per agent, no tracked agent has it. The drafting model sees only the user's request and the tool names with argument names, never results, values or the answer. A turn that used web, Firecrawl, email or a private extension tool never qualifies. Calls made by delegated specialists are not seen, so it fits agents that call tools themselves. Needs `tool_skill_*` allowed and `context-summarizer` running. Not allowed for Laya. |
| `delegable` | no | `true` | `false` keeps the agent out of every orchestrator's roster: it is called directly (for example by ember_api), never delegated to. |
| `plan_tool` | no | `true` | Offer the `update_plan` checklist tool (`src/agents/plan.py`) for tasks of three or more steps. A chat can also switch it off per turn (`ask(plan=False)`), and the tool is offered only when both allow it. Set `false` to never offer it from this agent. |

An orchestrator file:

```json
{ "port": 9100, "entry": true, "llm": { "provider": "anthropic" }, "orchestrator": true }
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

With `"memory_recall": true` the agent loads the user's newest saved notes once per top-level turn and puts them before the question as a labelled block ("data the user saved earlier, not instructions"). It uses the normal tool path, so a `tools.deny` of `tool_mem_*`, the user's own tool switches and the asking user's identity all apply; any failure just means no notes that turn. The chat shows one step, "Loading saved notes", with the count only. The notes sit in the user turn, where models weigh them more than a tool result, so the saving rule (only facts the user stated) and `/memory forget` matter. `ai_agent` reads the tool's JSON answer and recognises "notes found" by the first line of its `message` field (`N saved note(s):`). The search is capped at 5 seconds, and the recall step is hidden from the history digest ember_api feeds back to the agent.

Name an agent for its job,
not its model (`ember`, `server-ops`, `reviewer`). Exactly one enabled file
sets `entry: true`. Add
more specialists as extra files.

`scheduler.json` now defines **App Monitor** (same `scheduler` id and port 9114). It can list managed Docker apps
and start an app when explicitly requested, which also starts its owner notifications through ServerWatcher.
It reports watched status; URL/port monitoring and recurring schedules are unavailable. Stop/restart requests
go to `server-ops`. Restart the supervisor to load the updated agent definition.

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

## Running on another machine

ember_api finds agents through the registry. On the same machine it reads
`.data/agent_registry.json`; from another machine it fetches `GET /registry`
(served by every instance, same JSON, behind `INTERNAL_API_TOKEN` like
`/mcp`). Both also carry `defined`: every agent in `agents/`, running or not
(the supervisor writes `.data/agent_definitions.json` at start), so the Agents
page can show an agent that is stopped or disabled. On the ai_agent machine:

- `AI_AGENT_HOST=0.0.0.0` so it accepts outside connections.
- `AI_AGENT_ADVERTISE_URL=http://10.0.0.5` (an address peers can reach, no
  path). This is the address registered for each agent; without it a bind-all
  host registers as `127.0.0.1`. Leave the port out when the supervisor starts
  several agents: each one adds its own port. A value with a port is used as
  is (single instance).
- The same `INTERNAL_API_TOKEN` as ember_api, and the ports open in the
  firewall. Use a private network or TLS: the token travels in a header.

Then set `agents_registry_url` in `apps/Ember/ember_api/configs/config_app.json` (see
`apps/Ember/ember_api/configs/README.md`).

## Laya question agent

`agents/triage-assistant.json` defines a local specialist backed by Laya, a
small model that answers typed questions about a short text. It is part of the
tracked roster. The models run in the Laya service (see Laya models above);
set `enabled: false` if this installation should not run it. Restart the
supervisor after changing the roster. Its provider is `laya`, gateway `local`,
model `convaiinnovations/laya`; no cloud model or API key is used.

Laya never generates text. The caller supplies the questions as the `ask`
question, a JSON string:

```json
{
  "text": "SQLite database is locked",
  "min_confidence": 0.7,
  "questions": {
    "category": {"type": "choice", "instructions": "Which category?",
                 "criteria": {"database": "SQL and storage", "network": "Connections"}},
    "severity": {"type": "score", "instructions": "How severe?",
                 "criteria": ["none", "minor", "major"]},
    "problem":  {"type": "noul", "instructions": "Is there a problem?"}
  }
}
```

- `choice`: `criteria` is `{option: description}`, 2 to 10 options.
- `score`: `criteria` is a list of 2 to 10 level descriptions, lowest first.
  The answer is the expected level (0 to n-1) with a `legend`.
- `noul` (yes/no): `criteria` is optional `{"false": "...", "true": "..."}`.
  The answer is P(true).
- `text` is at most 4,000 characters; 1 to 8 questions; `min_confidence` is
  optional (default 0.70, `MIN_CONFIDENCE` in `src/llm/laya_provider.py`).
  Text after the JSON object is ignored.
- `local_only: true` (optional) keeps the request on Laya's own models: the English checkpoint, then the
  typed-decisions checkpoint when English is unsure, and never the fallback classifier (Jev), whatever `classifier`
  says. The service loads both models at its start-up. Unsure answers stay marked `uncertain`, and a text Laya cannot
  read whole is an error. ember_api's tag suggestions and triage questions and mcp_server's ticket grouping use it,
  so their text never leaves the machine.

The response is JSON: `{"answers": {id: {...}}, "uncertain": bool}`. Each
answer has `type`, the result (`choice`/`score`/`noul`), `answer_confidence`
and `uncertain` (confidence below `min_confidence`). A request with an unknown
field, type, or out-of-range size is rejected before inference with an
"Invalid Laya request" error. Garrison checks only the envelope (the JSON, `text`, `min_confidence`, `trace`,
`local_only`); the question rules above (types, `criteria` shapes, option and question counts) are the Laya
service's, checked with its `POST /v1/validate`, so there is one definition for every caller. If the service cannot
be reached the questions go unchecked and Jev, where allowed, may still answer.

The top-level `uncertain` is true if ANY answer is uncertain, so callers that
mix question types should read the per-answer `uncertain` flags (score
questions in particular tend to have lower confidence).

The English checkpoint has a 512-token limit including the question heads, so
keep texts and criteria short. Input Laya reports as truncated is rejected
instead of answering from partial evidence. At start-up the agent only checks that the Laya service answers
and logs a warning if not; the service downloads weights on its first start. Service errors
propagate without an LLM fallback (Jev below is a classifier, not an LLM answer). History is deliberately excluded and
`interpret`/summarization is unsupported. Cancellation is checked before and
after the service call.

### Triage flow (Laya English, Laya typed-decisions, Jev)

A request may carry `"strategy"`, using any name offered by Laya's `GET /v1/strategies`.
Resolution is the request value, then the admin default, then the existing voter settings.
When an override resolves, all questions use it in one service call. Unknown names are
invalid requests (422), including when `/v1/ask` rejects one after listing was unavailable;
these refusals never trigger Jev fallback.

The shared `src/core/tuning_overrides.py` reads the admin default from
`configs/config_tuning_overrides.json` on every request and writes it atomically.
`GET /agents/triage-strategy` returns `{default, strategies}`; `PUT` takes
`{strategy: string | null}` and returns the same shape. Both require the internal
token. Null clears the override and restores voter-derived behavior, independently
of the service's `auto` strategy. If Laya cannot list strategies, GET retains the
stored default with `strategies: []`; setting a name requires the service, while
clearing does not. The existing `config_tuning.json` remains authoritative for voters.

Every request goes through `src/llm/triage_flow.py` (the whole flow is written at the top of that file). Without an override, for each
question type Garrison reads the local voters that `classifier.triage_order` and `triage_enabled` allow and asks the
Laya service for the matching strategy: English then typed = `english-then-typed` (the default), typed first =
`typed-then-english`, one voter = `english-only` / `typed-only`. The service runs the local rules, each model against
its own confidence threshold by number of options left (2 options: English 0.90, typed 0.80; 3 or more: 0.75, 0.55),
changed with `classifier.triage_thresholds` (`{"3+": {"laya-typed": 0.6}}`) or, for one request, by sending
`min_confidence`. Between the steps it drops options far below the best (`triage_prune_ratio`) and asks again, and
when no model is ever sure it compares the models' confidence-weighted values pairwise (`triage_pair_ratio`): the
answer then carries `also_check`, or `"unknown": true` with `candidates`, and is always `uncertain`. Garrison sends
these settings and the window (`triage_window`) with every request. The rules and the other strategies
(`most-confident`, `average`, `consensus`) are in `LayaAgent/README.md`.

Jev (gated by `triage_fallback`, a key and the triage chain, see below) is asked only about what the service could
not settle, over the options it left, with a threshold of 0.90 (2 options and 3 or more alike, `triage_thresholds`
changes it). An unsure Jev is asked again once over the options all the models' averaged probabilities narrow to;
if nobody is sure, the service compares all the voters as above. Averaging and comparing are the service's
`/v1/combine`. Score questions take the first model that meets its 3+ threshold. A noul question uses the 2-option
thresholds, and Jev decides it only when typed is unsure and the fallback is on. If the service cannot be reached,
Jev answers alone (when allowed). A `local_only` request never reaches Jev.

Which models answer which question type, and in what order, is set per type in `configs/config_tuning.json`
(`classifier`; the `.example` shows the defaults):

```json
"triage_enabled": {"laya-english": {"noul": false}, "jev": {"score": false}},
"triage_order": {"noul": ["laya-typed", "jev"], "choice": ["laya-typed", "laya-english", "jev"]}
```

`triage_enabled` is voter -> type -> true/false (everything on by default). `triage_order` is type -> the voters asked,
first to last; a voter left out is never asked. English is left out of `noul` by default, because its true/false
labels can override the text (a confident "no" on clearly positive input). For a `choice` question the order is that of
the Laya models, and `jev` must be listed last: it is asked after the Laya models are done, including their narrowed
rounds. For `score` and `noul` the order is followed exactly. A type needs at least one voter that is both listed and
enabled, or the config is refused at start-up. Jev is still asked only when `triage_fallback`, a key and the triage
chain allow it.

The answer is compact by default, because the orchestrator reads it on every turn: `type`, the pick (`choice`, `score`
or `noul`), `answer_confidence`, `uncertain`, `answered_by`, `probabilities` (2 decimals) and, when they apply,
`also_check`, `unknown` and `candidates` (about 75 tokens for a reviewed question). Send `"trace": true` in a request,
or set `classifier.triage_trace`, for the full answer: also `resolved_by`, `eliminated`, `disagreement`, a `note` and a
`rounds` trace of every model call (about 480 tokens). `check_triage_cases --rounds` always reads the full one.

- Both checkpoints read `classifier.triage_window` tokens (default 4096). They live in the Laya service, which loads
  both at its start (the second downloads on first start, about 2 minutes) and needs roughly 1.6-3.4 GB of RAM per
  replica; Garrison itself needs none of it.
- The checks measured so far: English 20/23 and typed 21/23 on the 47 cases in `scripts/check_triage_cases.py` with
  Laya alone; both are confidently wrong on sarcasm and "the server room is on fire", where nothing asks Jev.
- An old `config_tuning.json` may still hold `triage_flow` or `triage_confidence_gap` (settings of the removed
  single-model flow); they are read and ignored.

### Optional remote fallback (decision layer)

With a `"classifier": {"triage_fallback": true}` section added to `configs/config_tuning.json` (it is not in the `.example` seed) and
a key for a backend of the `triage` chain in `.env`, the remote classifier (`src/llm/decision.py`, see
[Decision layer](#decision-layer-optional)) is the third voter of the flow above, asked about what both Laya models
cannot settle:

- a text Laya cannot read in full (over its window, or reported truncated) goes to the classifier for every
  question. `classifier.max_input_chars` (default 16000) caps what is sent, since a remote window is larger than Laya's.

The classifier only picks one option and reports a 0-100 confidence, which is no more calibrated
than Laya's. Score questions are sent as levels `0`, `1`, ... (lowest first), and a
noul question as `false` / `true`. If it fails, times out or has no key, Laya's
answer is returned as it was (or, for unreadable input, the usual "could not read"
error). Its prompt tokens are added to the turn's input tokens and the result's
`model_note` says which models helped. It is **off by default**: the text
sent to it leaves this machine and each call is billed by the backend. Laya is skipped in the
triage chain here, since it is the provider asking.

Escalating to a real LLM is otherwise the orchestrator's decision: when `uncertain` is
true it can answer itself or delegate to another specialist. `0.70` is an
experimental review gate, **not a calibrated accuracy claim**. Run
`python -m scripts.check_laya_triage` for ten real-model smoke examples using
a triage question set, then evaluate representative local inputs before
relying on the answers.

To exercise the whole triage setup (both Laya models, the fallback, narrowing, the `rounds` trace) without the
orchestrator, run `python -m scripts.check_triage_cases`: 47 cases that call the Triage Assistant's own
code, with `--list`, `--case NAME` (or a pattern such as `"escalate-*"`), `--rounds`, `--baseline` (Laya alone, for comparison), `--prune-ratio R` and
`--json` (full answers with their traces). It uses your `config_tuning.json` and `.env` and sends the
cases' texts to the fallback backend when that is on.
`--three-way` runs the flow over both checkpoints with `--threshold laya-typed:3+=0.6` to change one threshold; the exact flow is in `scripts/triage_three_way.py`;
`--max-len` sets the Laya window (default 4096) and `--baseline` leaves Jev out.

Usage reports the model's actual input-token work and zero generated output
tokens. Laya is restricted to a specialist with the pinned checkpoint and
local gateway; generation settings, an entry role, or an orchestrator role are
rejected at startup.

## Orchestrator

An agent with `orchestrator: true` gets the `delegate_to_agent` tool;
specialists never do. Each turn the orchestrator's roster is built from the
registry: every registered agent that is not an orchestrator (and never the
agent itself), as lines of `<id> - <label>: <focus>`. Because it is per turn,
a specialist that starts or stops shows up without a restart. A specialist with
tools of its own (`tools.allow`, apart from the ticket tools) is left out when
none of them is offered right now: its capability is switched off on mcp_server,
or the asking user switched the specialist off (`agent:<id>` in `disabled_tools`). A specialist with
no tools of its own always stays. If mcp_server's tool list cannot be read, or is
empty, nobody is left out. The
`agent_id` argument of `delegate_to_agent` is an enum of the roster ids. An
orchestrator may still answer directly when no specialist fits.

Specialist activity streams to the orchestrator's caller as `agent_start`,
`agent_end` and `agent_token` events, and a specialist's own `step_*`
events pass through stamped with its `agent_id`. A specialist's step ids can
collide with the orchestrator's, so consumers key on `(agent_id, id)`.

## Internal Router agent

`agents/router.json` defines the supervised internal Router on port 9117. It is
visible on both Agents pages, but cannot receive chat questions or appear in a
delegation roster. Ember Admin's existing Agents editor (`agents.manage`) controls
its enabled state, task switches, local voters, confidence thresholds, narrowing,
deadline, remote timeout, tier mapping and optional trace. Saves use the existing
machine-specific override and supervisor restart; Reset restores tracked defaults.

For a top-level entry/orchestrator turn with conversation history, Garrison first
asks the tool-free `context-summarizer` for a short routing brief. Router receives
that brief, the latest user message verbatim, and the authorized specialist roster.
If the helper is unavailable, times out, or returns an unusable brief, routing uses
up to 600 characters of the previous assistant message instead. First messages
need no summary call. Memory injection and full history are excluded from Router.
Router runs the same flow as Triage Assistant: Laya English, typed-decisions,
option narrowing and optional Jev. It returns independent agent and size decisions.
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
4,000 local subject characters, 16,000 remote subject characters, and at most nine
specialists plus `none`. Oversized rosters leave agent selection to Ember while
size selection may continue. Inputs are not silently truncated to fit. Short
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

`agents/context-summarizer.json` defines the supervised helper on port 9118.
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

### Classifier backend configuration

The shared `classifier` section still configures Triage Assistant and the Jev
backend chain Router uses for remote fallback. Router's own voting policy is the
`decision` block of its agent definition and Admin override; it does not mutate
Triage Assistant's cached settings.

| Backend | Transport | Deployment credential |
| --- | --- | --- |
| `jev` | TypeSafe Jev API, default model `jev-latest` | `TYPESAFE_API_KEY` |
| `jev_vercel` | Vercel AI Gateway, default model `typesafe-ai/jev` | `VERCEL_GATEWAY_API_KEY` |
| `laya` | Existing local classifier helper | none |

`classifier.auto_route`, `classifier.auto_tier` and their feature-specific chains
are accepted for compatibility but no longer control automatic entry-turn
routing. Their reusable helper functions remain available for comparison tests.
Configure Router in Agents instead. Remote fallback sends the routing subject to
the selected provider and uses that provider's billing.

Run `python -m scripts.check_router_cases --offline` for deterministic contract
fixtures. It does not measure model accuracy. The explicit `--live` comparison
uses installed local models and environment credentials, records outcomes,
abstentions, elapsed time and remote calls, and never executes specialist work.
See [router-evaluation.md](docs/router-evaluation.md) before deployment activation.

## Usage log

Every completed `ask` appends one JSON line to
`.data/usage/YYYY-MM-DD.<agent id>.jsonl` (UTC date; one file per agent per
day, so no two processes write the same file). Each line is the `agent_usage`
row the `ask` result carries, plus `request_id` and `depth`:

- `agent_id`, `agent_label`
- `provider_id`, `gateway` (`null` when the provider is used directly), `model`
- `input_tokens`, `output_tokens`, `total_tokens`
- `started_at`, `finished_at` (UTC ISO-8601 with milliseconds)
- `prompt` is added to the row the `ask` result returns, not to the file: the history and question this agent received as `{role, content}` messages (`core/usage_log.prompt_messages`). A delegate's row therefore carries the question its orchestrator sent. The system prompt is never included. ember_api stores it for the Advanced chat-turn view.
- `delegated_by` (`null` for the top-level agent)
- `request_id`, `depth`

Set `AI_AGENT_USAGE_DIR` to write somewhere else. A cancelled turn writes no
line; only completed asks do. A write failure logs a warning and never fails
the turn. `.data/usage/` is gitignored.

## Tools and agents the user switched off

`ask` also takes `disabled_tools`: `agent:<id>` entries for specialists the asking user switched
off for their own chats (the roster leaves them out and `delegate_to_agent` refuses them), plus mcp_server tool names (`src/core/tool_filter.py`). For that turn the agent does
not offer them (`list_tools`) and refuses a call to one the model names anyway.
A delegated agent is told the same list. `status()` reports `tool_filter: true`
so ember_api can refuse an agent that would ignore the option.
`disabled_tools: ["*"]` blocks every built-in, shared-extension, and private-extension
tool when the Ember account lacks `tools.execute`. `status()` also reports
`tool_filter_all: true`; ember_api and delegates refuse older agents without it
before starting a restricted turn. The filter follows nested delegation.

`ask` also accepts `private_extensions`, the user's own MCP servers for this
turn; see the next section for its shape and behavior.

## Private extensions

A private extension is a user's own MCP server, passed to `ask()` per turn by
ember_api. Its tools belong to that account and turn only. Private extensions
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
ember_api can refuse an older agent that would ignore the argument. Laya
agents report `false`: they use no tools and do not support
private extensions.

## Asking before tools run

`ask` takes `approval_mode` and `allowed_tools` (`src/core/approvals.py`):

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
(ember_api) can refuse an older agent that would ignore the option.

`ask(ask_user=True)` offers the top-level agent clickable questions; answer or
skip through `answer_question(request_id, step_id, answers, skipped)`. Questions
emit `question_request` / `question_resolved`, wait up to 60 minutes with
keepalive events, and Stop cancels the turn. `status()` reports `user_questions: true`.

`ask(plan=False)` withholds the `update_plan` checklist tool for a turn, and `ask(plan_lean=False)` drops the instruction to update it only when an item changes status (with it on, an unchanged list is also skipped without an event). Both default on and are sent to specialists too; `status()` reports `plan_toggle: true`.

`ask(exact_context=True)` counts what fills the context window with the provider's own token counter (`src/llm/context_breakdown.py`; Anthropic `count_tokens`, OpenAI `responses.input_tokens`) instead of estimating it at about four characters a token. The result's `context_breakdown` lists the parts (system prompt, delegable agents, built-in tools, MCP tools, messages) and `context_breakdown_exact` says whether the provider counted them. Counts are cached by model and content, so only the first turn after a change to the prompt, the tools or the model makes requests; any failure or a 3 second wait falls back to the estimate, so counting never fails a turn. `status()` reports `exact_context: true`.

## Prompts

Each agent's system prompt comes from its own `agents/<id>.json`, in this order:

1. An identity line, `Your name is Ember: <role>`. The role is `Orchestrator`
   for an orchestrator, else the file's `label` (`Ember: Researcher`,
   `Ember: Reviewer`).
2. `persona`.
3. For an orchestrator, the roster of specialists, rebuilt each turn.
4. `instructions`. Empty uses `DEFAULT_INSTRUCTIONS` in `src/llm/agent_roles.py`.

There is no shared prompt file. Edit the agent's file and restart it.

Agent files give each instance its own id, so any number of same-provider agents can run side by side.

## Security

- **`/mcp` needs the internal token** once `INTERNAL_API_TOKEN` is set in
  `.env` (created from its `.example` on first
  run; same value as mcp_server's, chat_app's and ember_api's). Without it
  a request gets `401`. The agent sends the same token on its own calls to
  mcp_server and to peer agents (`src/core/internal_auth.py`).
- **The asking user travels on**: `ask()` reads `X-Requester-Username` /
  `X-Requester-Email` from the request (ember_api and chat_app set them),
  and every mcp_server tool it calls during that turn gets the user in the
  call's `_meta.requester` - the agent's one mcp_server session is shared by
  every user, so a header can't carry it. A delegated agent gets it as
  headers. The model never sets either.

## Project layout

- **`agents/*.json`** - tracked default agent definitions; admin UI changes go
  to the untracked `.data/agent_overrides.json` instead. See [`agents/README.md`](agents/README.md).
- **`gateways/<provider>/*.json`** - tracked individual gateway presets,
  read directly. See [`gateways/README.md`](gateways/README.md).
- **`configs/*.json`** - structured settings, mostly gitignored. See
  [`configs/README.md`](configs/README.md).
- **`.env`** - the one credentials file (provider, gateway, role, API
  keys, `INTERNAL_API_TOKEN`), gitignored; copy it from `.env.example`.

See [`src/README.md`](src/README.md) for the full code map - what lives
where, and where new code goes.

See
[`docs/superpowers/specs/2026-09-07-ai-agent-mcp-layer-design.md`](../docs/superpowers/specs/2026-09-07-ai-agent-mcp-layer-design.md)
for the full design rationale.

## Scoped second-brain auto-save

Ember's auto-save destination travels as trusted `X-Brain-Destination` identity
metadata, then as `requester.brain_scope` on Armory calls and headers to delegated
agents. A model cannot change a constrained personal/instance write destination.
Normal calls retain their previous metadata shape when no destination is bound.
See [Obsidian brains](../../docs/obsidian-brains.md).
