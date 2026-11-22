# chat_cli

A terminal chat with an ember agent. It logs in to [portcullis](../Ember/portcullis/README.md) with your
account and works like the web chat: every question goes to portcullis's entry agent, which hands
work to specialist agents, and answers stream as they are written, with
tool progress, saved chats, usage limits and tool approvals. It is an interactive program,
not a server, so it has no compose service.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- portcullis running (and ai_agent behind it), and an ember account whose email is verified.

## Run

```bat
uv sync
uv run python -m src.main
uv run python -m src.main --user ada
uv run python -m src.main --url http://127.0.0.1:29601 --ask
```

`uv sync` creates `.venv` and installs once; afterwards only the `uv run` lines.

| Option | Meaning |
|---|---|
| `--url URL` | portcullis's address (default: `configs/config_cli.json`, else `http://127.0.0.1:29601`) |
| `--user NAME` | the account to log in as (default: the config, else asked) |
| `--ask` | ask before each tool runs (same as `/ask on`) |

There is no password option on purpose: the password is typed at the prompt (hidden), kept
only in memory, and never written anywhere. Three wrong tries end the program; a lockout
(too many failed logins) is shown with portcullis's own message.

## Using it

Type a question and press Enter. The answer streams in as Markdown; each tool the agent runs
shows as `⏳ name` and then `✓` (or `✗` with the first line of what went wrong). A footer shows
the agent, model, tokens and time. Every question and answer is saved by portcullis, so the chat
is also in the web page, and the web page's chats are here.

| Command | What it does |
|---|---|
| `/chats` | list your recent chats (30 newest) |
| `/open N` | open chat N from that list; if it is still answering, join it |
| `/new` | start a new chat |
| `/ask on\|off` | ask before each tool runs (off by default) |
| `/usage` | your tokens against the 6-hour and weekly limits |
| `/help`, `/quit` | |

Any other `/...` is not sent: the tool slash commands of the web chat are not supported here.

- **Ctrl+C while an answer is being written** stops it (portcullis is told to cancel) and
  returns to the prompt. At the prompt, Ctrl+C warns once and a second press leaves; Ctrl+D
  leaves at once.
- **Tool approvals.** With `/ask on`, or when an administrator requires approval for everyone,
  the agent's tool runs wait for you: the tool and its arguments are shown, then
  `[y]es once, [a]lways for this chat, [n]o`. Anything but y or a is a no. "Always" is not
  offered while an administrator requires approval for every tool. No answer within four minutes
  counts as no on the server.
- **A lost connection** to portcullis is retried after 0.5, 1, 2, 4 and 8 seconds, resuming
  where it left off; after that the answer carries on on the server and you can read it with
  `/chats`. A session that ended (portcullis restarted, or it expired) asks for the password again.
- On a console that cannot show Unicode the marks fall back to `[..]`, `[ok]`, `[x]`.

Not here: attachments, summaries, regenerate and edit, branching, sharing, prompt templates.

## Configuration

`configs/config_cli.json` (tracked; see `configs/README.md`):

```json
{ "ember_api_url": "http://127.0.0.1:29601", "username": "" }
```

## Layout

```
src/
  main.py       arguments, login, wiring
  config.py     the settings file
  api.py        EmberClient: portcullis's REST calls and event stream (httpx)
  sse.py        Server-Sent Events parser
  events.py     watch_turn: reconnect, resume, give up
  session.py    which chat and agent are open
  renderer.py   StreamRenderer: draws events with rich
  repl.py       ChatRepl: the prompt loop, commands, one turn
tests/          pytest; no network (fake portcullis through httpx's MockTransport)
```

## Tests

```bat
uv run pytest
```

The tests use a fake portcullis and a scripted prompt. The client was also run once against a real
portcullis (its own code, a temporary database and a fake agent): login, the agent list, a streamed
answer with a tool approval, `/chats`, `/open`, `/usage`, logout. That run predates portcullis's switch to
one entry agent (`GET /api/agent`); chat_cli now asks for the entry agent and has no agent picker.
