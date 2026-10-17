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

2. Make sure `mcp_server` is running (`apps/mcp_server/run.bat`) -
   `apps/ai_agent/configs/config_servers.json` points at its default
   `http://127.0.0.1:8010/mcp`.

3. Start the agents with `run.bat` (from `apps/ai_agent/`). It creates
   `.venv_ai_agent` and installs this project into it in editable mode on
   first run, then runs `py -m src.supervisor`. See Agents below.

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
| `plan_tool` | no | `true` | Offer the `update_plan` checklist tool (`src/agents/plan.py`) for tasks of three or more steps. A chat can also switch it off per turn (`ask(plan=False)`), and the tool is offered only when both allow it. Set `false` to never offer it from this agent. |

An orchestrator file:

```json
{ "port": 9100, "entry": true, "llm": { "provider": "anthropic" }, "orchestrator": true }
```

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

`run.bat` starts all agents: it runs `python -m src.supervisor`, which
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
  host registers as `127.0.0.1`. Leave the port out when `run.bat` starts
  several agents: each one adds its own port. A value with a port is used as
  is (single instance).
- The same `INTERNAL_API_TOKEN` as ember_api, and the ports open in the
  firewall. Use a private network or TLS: the token travels in a header.

Then set `agents_registry_url` in `apps/Ember/ember_api/configs/config_app.json` (see
`apps/Ember/ember_api/configs/README.md`).

## Laya question agent

`agents/triage-assistant.json` defines a local specialist backed by Laya, a
small model that answers typed questions about a short text. It is part of the
tracked roster. Laya is a regular dependency, installed with `pip install -e .`;
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

The response is JSON: `{"answers": {id: {...}}, "uncertain": bool}`. Each
answer has `type`, the result (`choice`/`score`/`noul`), `answer_confidence`
and `uncertain` (confidence below `min_confidence`). A request with an unknown
field, type, or out-of-range size is rejected before inference with an
"Invalid Laya request" error.

The top-level `uncertain` is true if ANY answer is uncertain, so callers that
mix question types should read the per-answer `uncertain` flags (score
questions in particular tend to have lower confidence).

The English checkpoint has a 512-token limit including the question heads, so
keep texts and criteria short. Input Laya reports as truncated is rejected
instead of answering from partial evidence. The model loads before the agent
registers as running; the first load may download weights. Loading/inference
errors propagate without an LLM fallback (Jev below is a classifier, not an LLM answer). History is deliberately excluded and
`interpret`/summarization is unsupported. Cancellation is checked before and
after inference.

### Optional remote fallback (decision layer)

With a `"classifier": {"triage_fallback": true}` section added to `configs/config_tuning.json` (it is not in the `.example` seed) and
a key for a backend of the `triage` chain in `.env`, the remote classifier (`src/llm/decision.py`, see
[Decision layer](#decision-layer-optional)) answers what Laya cannot:

- each question Laya marks `uncertain` is asked again. For a `choice` question the two confidences are compared
  first: if they differ by at least `classifier.triage_confidence_gap` (default 0.3), the more confident
  model's answer stands as it is (`"deferred_to"` names it) and nothing is averaged. Otherwise Laya's answer is
  weighed with the classifier's instead of being thrown away: the two probability sets are averaged and
  options far below the rest (under `classifier.triage_prune_ratio`, default 0.25, of the leader's
  average; 0 turns it off; at least two always stay) are dropped. The question is then asked again over
  the options left, Laya first and the classifier only if Laya is still unsure. The answer lists what
  was dropped in `"eliminated"` (those options read 0) and `"answered_by"` says who decided (`laya`,
  `jev`...). If nothing is far enough below, the two answers are blended instead
  (`"answered_by": "laya+jev"`): the higher confidence when both pick the same option, the lower one and
  an `"uncertain": true` plus a `"disagreement"` object (who picked what) when they differ.
  With exactly two options left (a two-option question, or after dropping) and the two models still picking
  differently, each model's probabilities are multiplied by its own confidence, the two results are
  subtracted per option and the absolute differences compared: when the smaller one is under
  `classifier.triage_pair_ratio` (default 0.5) of the larger, the option with the bigger difference is the answer
  (`"resolved_by": "pair"`, `"probabilities"` are the shares of the two differences); otherwise the answer is
  unsure and lists both options in `"candidates"`. Both carry a `"disagreement"` object, `"also_check"` (the
  option the reader should still look at, the loser) and a one-line `"note"` saying so.
  Such an answer carries a `"rounds"` trace, one entry per model call in order (`laya`, the classifier,
  `average` with what it dropped, then the narrowed `laya` and, if needed, classifier calls with their
  `options`): each shows its pick, probabilities and confidence, and a Laya that could not take the
  narrowed question is recorded as `failed`. It costs a few hundred characters of the answer.
  `score` and `noul` questions take the classifier's answer as it is;
- a text Laya cannot read in full (over its 4000 characters, or reported truncated)
  goes to the classifier for every question. `classifier.max_input_chars` (default 16000) caps
  what is sent, since a remote window is larger than Laya's.

The classifier only picks one option and reports a 0-100 confidence, which is no more calibrated
than Laya's. Score questions are sent as levels `0`, `1`, ... (lowest first), and a
noul question as `false` / `true`. If it fails, times out or has no key, Laya's
answer is returned as it was (or, for unreadable input, the usual "could not read"
error). Its prompt tokens are added to the turn's input tokens and the result's
`model_note` says how many answers came from it. It is **off by default**: the text
sent to it leaves this machine and each call is billed by the backend. Laya is skipped in the
triage chain here, since it is the provider asking.

Escalating to a real LLM is otherwise the orchestrator's decision: when `uncertain` is
true it can answer itself or delegate to another specialist. `0.70` is an
experimental review gate, **not a calibrated accuracy claim**. Run
`python -m scripts.check_laya_triage` for ten real-model smoke examples using
a triage question set, then evaluate representative local inputs before
relying on the answers.

To exercise the whole triage setup (Laya, the fallback, narrowing, the `rounds` trace) without the
orchestrator, run `python -m scripts.check_triage_cases`: 17 cases that call the Triage Assistant's own
code, with `--list`, `--case NAME`, `--baseline` (Laya alone, for comparison), `--prune-ratio R` and
`--json` (full answers with their traces). It uses your `config_tuning.json` and `.env` and sends the
cases' texts to the fallback backend when that is on.

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
or the asking user switched those tools off (`disabled_tools`). A specialist with
no tools of its own always stays. If mcp_server's tool list cannot be read, or is
empty, nobody is left out. The
`agent_id` argument of `delegate_to_agent` is an enum of the roster ids. An
orchestrator may still answer directly when no specialist fits.

Specialist activity streams to the orchestrator's caller as `agent_start`,
`agent_end` and `agent_token` events, and a specialist's own `step_*`
events pass through stamped with its `agent_id`. A specialist's step ids can
collide with the orchestrator's, so consumers key on `(agent_id, id)`.

## Decision layer (optional)

`src/llm/decision.py` answers "which option fits, and how sure" for three features: Laya's
`triage` fallback, `auto_tier` and `auto_route`. A feature names a chain of backends in
`classifier.chains` of `configs/config_tuning.json`; the default chain is `["jev", "jev_vercel"]`.
The chain is walked in order, so a backend without a key, one that fails, or (for `auto_tier`
and `auto_route`) one below the feature's `min_confidence` hands over to the next, and the last
answer is returned. Every feature is off until its own setting turns it on.

| Backend id | Module | What it is | Key in `.env` |
|---|---|---|---|
| `jev` | `typesafe_classifier.py` | TypeSafe's own Jev API (`/v1/systemone`, `typesafe.model` default `jev-latest`). Confidence is the API's 0-1 `confidence` (how peaked the probabilities are) as a percentage. | `TYPESAFE_API_KEY` |
| `jev_vercel` | `jev_classifier.py` | `typesafe-ai/jev` through Vercel AI Gateway; the model reports its own 0-100 confidence. | `VERCEL_GATEWAY_API_KEY` |
| `laya` | `laya_classifier.py` | The local Laya model (512-token window). A text or option list that does not fit hands over to the next backend. Not in the default chains. | none |

```json
"classifier": {
  "chains": {"triage": ["jev", "jev_vercel"], "auto_tier": ["laya", "jev"], "auto_route": ["jev"]},
  "typesafe": {"model": "jev-latest"},
  "vercel": {"url": "https://ai-gateway.vercel.sh/v1/chat/completions", "model": "typesafe-ai/jev"}
}
```

A new model is one module with `ID`, `available()` and `ask_choice(subject, criteria, question, timeout)`
plus a line in `decision._BACKENDS`. Confidence means something different per backend, so tune
each feature's `min_confidence` against the backend you chain, not against the 60 default.

## Automatic model tier (optional)

With `"classifier": {"auto_tier": {"enabled": true}}` in `configs/config_tuning.json` and
a key for a backend of the `auto_tier` chain in `.env`, a top-level turn that asked for no tier gets one from how
hard its question looks. The classifier (`src/llm/decision.py`) names the
request `tiny`, `everyday`, `large` or `hardest`, and `src/llm/auto_tier.py` maps that to a
tier (default `tiny` and `everyday` to `light`, `large` to `standard`, `hardest` to
`heavy`; change it under `auto_tier.tiers`). `agent_config.run_chat` then resolves it
like a delegated tier, so the agent's own `min_tier` / `max_tier` still cap it: an agent
capped at `light` stays on `light`, and raising `max_tier` is what lets a hard question
use a stronger model.

It is skipped, and the default model runs, when the feature is off, there is no key, the
classifier fails, its confidence is below `auto_tier.min_confidence` (default 60), the turn
is a delegate's or already asked for a tier, the agent has no tiers, or the message is a
short follow-up (under 20 characters after the chat's first message). A chosen tier shows
as the turn's tier plus a `model_note` such as `auto tier: hardest (90%) -> heavy`. Only the
user's question is sent, never tool results, but it does leave this machine and each call
is billed by the backend.

## Routing straight to a specialist (optional)

With `"classifier": {"auto_route": {"enabled": true}}` in `configs/config_tuning.json` and
a key for a backend of the `auto_route` chain in `.env`, an orchestrator's top-level turn first asks the
classifier (`src/llm/decision.py`) which specialist fits the question
(`src/agents/auto_route.py`). If one is picked with confidence of at least
`auto_route.min_confidence` (default 60), the question goes to it exactly as a
`delegate_to_agent` call would (same `step_*` and `agent_*` events, same usage rows) and its
answer is the turn's answer; the orchestrator's own model never runs. Its usage row then
holds only the classifier's tokens, and `model_note` reads `routed straight to <label>`.

- Only specialists with tools of their own are offered, among the ones the roster already
  shows this turn (capabilities off, or tools the user switched off, hide them). Tool-less
  helpers such as `planner` stay the orchestrator's to choose.
- The classifier sees the user's message and the end of the last assistant message; the
  specialist gets the same context, since it never sees the chat.
- No routing, and the orchestrator answers as usual, when the feature is off, there is no
  usable backend, the classifier fails or says `none`, confidence is low, the turn is a delegate's, or
  the turn would need the user's approval to delegate (the orchestrator then asks as it does today).
- A specialist that fails is reported to the user and not retried, because it may already
  have acted. You also lose the orchestrator's synthesis of the answer on routed turns.
- The text sent to the classifier leaves this machine and each call is billed by the backend.

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

## Tools the user switched off

`ask` also takes `disabled_tools`: mcp_server tool names the asking user switched
off for their own chats (`src/core/tool_filter.py`). For that turn the agent does
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
