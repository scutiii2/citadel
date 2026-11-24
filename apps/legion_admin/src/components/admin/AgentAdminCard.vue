<script setup lang="ts">
import ActionMessage from "./ActionMessage.vue";
import { computed } from "vue";
import type { AgentFile, AgentStatus, AgentTier, LiveAgent } from "../../api/AgentsAdminClient";

/** Configured settings and live model details for the selected agent. */
const props = defineProps<{ agent: AgentFile; status?: AgentStatus; tiers?: AgentTier[]; decision?: LiveAgent["decision"] }>();
defineEmits<{ remove: []; reset: [] }>();

const STATUS_TEXT: Record<AgentStatus, string> = { running: "Running", offline: "Offline", disabled: "Disabled" };
const STATUS_ICON: Record<AgentStatus, string> = { running: "●", offline: "○", disabled: "–" };

const shownStatus = computed<AgentStatus | undefined>(() => props.agent.enabled === false ? "disabled" : props.status);
const gatewayOrder = computed(() => {
  const llm = props.agent.llm;
  if (!llm) return "";
  const defaults: Record<string, string> = { anthropic: "claude", openai: "gpt" };
  const primary = llm.gateway || defaults[llm.provider];
  return [primary, ...(llm.fallback_gateways ?? []).map((choice) =>
    typeof choice === "string" ? choice : choice.gateway)].filter(Boolean).join(" → ");
});
type Row = { label: string; value: string };
const present = (rows: { label: string; value: unknown }[]): Row[] =>
  rows.map((row) => ({ label: row.label, value: Array.isArray(row.value) ? row.value.join(", ") : row.value === undefined || row.value === null ? "" : String(row.value) }))
    .filter((row) => row.value !== "");
const rows = computed(() => present([
  { label: "Provider", value: props.agent.llm?.provider },
  { label: props.agent.llm?.provider === "decision" ? "Strategy" : props.agent.llm?.fallback_gateways?.length ? "Gateway order" : "Gateway",
    value: props.agent.llm?.provider === "decision" ? props.agent.decision?.strategy ?? props.agent.llm.strategy ?? "both" : gatewayOrder.value },
  { label: "Model", value: props.agent.llm?.model },
  { label: "Effort", value: props.agent.llm?.reasoning_effort },
  { label: "Tier range", value: props.agent.llm?.min_tier || props.agent.llm?.max_tier
    ? `${props.agent.llm?.min_tier ?? "any"} to ${props.agent.llm?.max_tier ?? "any"}` : "" },
  { label: "Temperature", value: props.agent.llm?.temperature },
  { label: "Max tokens", value: props.agent.llm?.max_tokens },
]));
const general = computed(() => present([
  { label: "Role", value: props.agent.role },
  { label: "Kind", value: props.agent.kind },
  { label: "Enabled", value: props.agent.enabled === false ? "No" : "Yes" },
  { label: "Port", value: props.agent.port },
  { label: "URL", value: props.agent.url },
  { label: "Source", value: props.agent.overridden ? "Edited on this machine" : "Tracked default file" },
]));
const limits = computed(() => present([
  { label: "Tool rounds", value: props.agent.llm?.max_tool_rounds },
  { label: "Turn tokens", value: props.agent.llm?.max_turn_tokens },
  { label: "Turn seconds", value: props.agent.llm?.max_turn_seconds },
  { label: "Highest delegated effort", value: props.agent.llm?.max_effort },
  ...Object.entries((props.agent.limits as Record<string, unknown> | undefined) ?? {}).map(([key, value]) => ({ label: key.replace(/_/g, " "), value })),
]));
const access = computed(() => present([
  { label: "Delegates to", value: props.agent.workers },
  { label: "Tools allowed", value: props.agent.tools?.allow },
  { label: "Tools denied", value: props.agent.tools?.deny },
  { label: "Plan tool", value: props.agent.plan_tool === false ? "Off" : "" },
]));
const sections = computed(() => [
  { title: "General", rows: general.value }, { title: "Model", rows: rows.value },
  { title: "Run limits", rows: limits.value }, { title: "Delegation and tools", rows: access.value },
].filter((section) => section.rows.length));
</script>

<template>
  <article :class="['agent-card', shownStatus, { entry: agent.entry }]" data-test="agent" :data-id="agent.id">
    <div class="head">
      <div class="admin-record-name">
        <span class="admin-record-badge" aria-hidden="true">{{ (agent.label || agent.id).slice(0, 2).toUpperCase() }}</span>
        <div><h3>{{ agent.label || agent.id }}</h3><code>{{ agent.id }}</code></div>
      </div>
      <span class="status"><span aria-hidden="true">{{ shownStatus ? STATUS_ICON[shownStatus] : '○' }}</span> {{ shownStatus ? STATUS_TEXT[shownStatus] : 'Unknown' }}</span>
    </div>
    <div v-if="agent.entry || agent.role === 'orchestrator' || agent.role === 'router'" class="tags">
      <span v-if="agent.role === 'router'" class="tag">Internal / Router</span>
      <span v-if="agent.entry" class="tag entry-tag">Entry</span>
      <span v-if="agent.role === 'orchestrator'" class="tag">Orchestrator</span>
    </div>
    <ActionMessage v-if="agent.error" kind="error" :text="agent.error" />
    <template v-else>
      <p class="focus">{{ agent.focus || "No description." }}</p>
      <p v-if="agent.role === 'router'" class="focus">
        {{ agent.decision?.strategy === "jev-only" ? "Jev only" : agent.decision?.strategy === "laya-only" ? "Local Laya only" : "Local Laya → Jev fallback" }}.
        Agent and model decisions are configured in Edit.
        <template v-if="decision?.fallback_available === false">Jev fallback unavailable: check the deployment credentials.</template>
        <template v-if="decision?.local_status === 'unavailable'">Local checkpoints unavailable: prepare the cached models.</template>
      </p>
      <section v-for="section in sections" :key="section.title" class="llm" :data-test="`section-${section.title}`">
        <h4>{{ section.title }}</h4>
        <dl>
          <template v-for="row in section.rows" :key="row.label">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
          </template>
        </dl>
        <ul v-if="section.title === 'Model' && tiers?.length" class="tiers" aria-label="Model tiers">
          <li v-for="t in tiers" :key="t.tier">
            <span class="tier" :title="t.use_for">{{ t.tier }}</span>
            <span class="tier-model" :title="t.use_for">{{ t.id }}</span>
          </li>
        </ul>
      </section>
      <section v-if="agent.persona" class="llm">
        <h4>Persona</h4>
        <p class="persona">{{ agent.persona }}</p>
      </section>
    </template>
    <div class="buttons">
      <button
        v-if="agent.overridden"
        type="button"
        class="chip"
        data-test="reset"
        title="Discard this machine's edits and use the tracked default file"
        @click="$emit('reset')"
      >Reset to defaults</button>
      <button
        type="button"
        class="remove"
        data-test="remove"
        :disabled="agent.entry === true"
        :title="agent.entry ? 'The entry agent cannot be removed. Make another agent the entry first.' : undefined"
        @click="$emit('remove')"
      >Remove</button>
    </div>
  </article>
</template>

<style scoped>
.agent-card { display: flex; flex-direction: column; gap: 8px; max-width: 720px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
h3 { margin: 0; font-size: 1.2em; font-weight: 600; color: var(--text); }
.status { flex-shrink: 0; font-size: 0.8em; color: var(--muted); }
.running .status { color: var(--success); }
.head .admin-record-badge { width: 44px; height: 44px; color: var(--accent); }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { padding: 1px 8px; border-radius: var(--radius-sm); font-size: 0.75em; color: var(--muted); background: var(--code-bg); }
.tag.entry-tag { color: var(--accent-contrast); background: var(--accent); }
.focus {
  margin: 0;
  font-size: 0.9em;
  overflow-wrap: anywhere;
}
.problem { margin: 0; color: var(--danger); font-size: 0.9em; overflow-wrap: anywhere; }
.llm {
  margin: 4px 0 0;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  font-size: 0.8em;
}
.llm { display: flex; flex-direction: column; gap: 6px; }
h4 { margin: 0; font-size: 0.85em; font-weight: 600; color: var(--text); }
.persona { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--muted); }
dl, .tiers { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; margin: 0; }
.tiers { padding: 0; list-style: none; }
.tiers li { display: contents; }
dt, .tier { color: var(--muted); }
dd, .tier-model { margin: 0; font-family: var(--mono); overflow-wrap: anywhere; }
.buttons { display: flex; gap: 8px; margin-top: 12px; padding-top: 16px; border-top: 1px solid var(--border); }
.chip { padding: 4px 12px; border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; color: var(--text); font: inherit; cursor: pointer; }
.remove { padding: 4px 12px; border: 1px solid var(--danger); border-radius: var(--radius-full); background: transparent; color: var(--danger); font: inherit; cursor: pointer; }
.remove:disabled, .chip:disabled { opacity: 0.5; cursor: default; }
:is(button):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
