# agents/

Each tracked `<id>.json` defines one agent: the shared default. The admin UI
never writes these files. Its edits (model, tier caps, `enabled`, persona, a
new agent...) go to the untracked `../.data/agent_overrides.json`
(`{id: <whole agent file>}`), which replaces the tracked file for that agent on
this machine, so per-machine choices stay out of Git. Edit the tracked file by
hand to change the shared default; it is shadowed here while an override
exists. Deleting an agent in the admin UI removes both. There are no template
copies or startup seeding.

The committed roster includes Ember as its enabled entry agent and the
existing specialists. Every enabled agent needs a distinct port, and exactly
one enabled agent must set `entry: true`. Add an agent by creating a new file
or copying a definition to a new id and adjusting its port and role. Disable
an agent with `enabled: false`.

An agent's `llm.provider` and `llm.gateway` refer to
`../gateways/<provider>/<gateway>.json`; Laya's `local` gateway is built in.
Keep credentials in `../.env`. Ports, URLs, persona text and instructions in
these definitions are repository content, so review them before committing.
See `../README.md` for the field descriptions and examples.

The supervisor watches this directory and the overrides file and reconciles
validated changes.

`context-summarizer.json` is a tool-free, non-delegable light-tier helper for
Router context briefs and Ember's manual/automatic conversation compaction.
It is called directly through `interpret`; it does not choose agents or tiers.
`.data/agent_definitions.json` is its generated summary of all configured
agents; `.data/agent_registry.json` records registered running instances.
Both remain ignored runtime state, along with usage logs. Temporary admin
write files are ignored too.
