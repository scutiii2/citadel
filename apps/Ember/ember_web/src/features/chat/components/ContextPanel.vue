<script setup lang="ts">
import { computed } from "vue";
import type { AgentUsage, ContextPart } from "../../../api/types";
import { CONTEXT_ACCURACY_OPTIONS, type ContextAccuracy } from "../utils/contextAccuracy";
import { compactNumber } from "../../../utils/analytics/usageFormat";
import SegmentedControl from "../../../components/ui/forms/SegmentedControl.vue";

/** What fills the agent's context window: one stacked bar and a row per part
 * (system prompt, tools, messages ...), then the free space left. The parts are
 * the agent's own estimate; they add up to the tokens the model reported. */
const props = defineProps<{
  /** Tokens the last answer's prompt used. */
  tokens: number;
  /** The model's context window. */
  window: number;
  parts: ContextPart[];
  /** The parts were counted by the model provider, not estimated. */
  exact?: boolean;
  /** Each call's prompt cost; these do not fill the answering agent's window. */
  agentUsage?: AgentUsage[];
  /** How the next questions are counted; leave out to hide the switch. */
  accuracy?: ContextAccuracy;
}>();

const emit = defineEmits<{ "update:accuracy": [value: ContextAccuracy] }>();

const choice = computed<ContextAccuracy>({
  get: () => props.accuracy ?? "estimate",
  set: (value) => emit("update:accuracy", value),
});

interface Row {
  id: string;
  label: string;
  tokens: number;
  /** Share of the whole window, in percent. */
  percent: number;
  free: boolean;
}

const percentOf = (tokens: number): number => (props.window > 0 ? (tokens / props.window) * 100 : 0);

const rows = computed<Row[]>(() => {
  const used = props.parts.map((p) => ({ ...p, percent: percentOf(p.tokens), free: false }));
  const free = Math.max(0, props.window - props.tokens);
  return [...used, { id: "free", label: "Free space", tokens: free, percent: percentOf(free), free: true }];
});

const usedPercent = computed(() => Math.min(100, Math.round(percentOf(props.tokens))));

/** Each kind of part has its own colour, so a part keeps it whichever others are present.
 * An id this page does not know gets the neutral one. */
function partColor(id: string): string {
  return `var(--part-${id}, var(--part-other))`;
}

function formatPercent(percent: number): string {
  return percent > 0 && percent < 0.1 ? "<0.1%" : `${percent.toFixed(1)}%`;
}
</script>

<template>
  <div class="context-panel" role="dialog" aria-label="Context breakdown" data-test="context-panel">
    <template v-if="window > 0 && parts.length">
    <p class="summary">
      <strong>{{ usedPercent }}% used</strong>
      <span>{{ compactNumber(tokens) }} / {{ compactNumber(window) }}</span>
    </p>
    <div class="bar" aria-hidden="true">
      <i
        v-for="row in rows.filter((r) => !r.free)"
        :key="row.id"
        :style="{ width: `${row.percent}%`, background: partColor(row.id) }"
      />
    </div>
    <ul class="rows">
      <li v-for="row in rows" :key="row.id" :data-part="row.id">
        <i class="swatch" :class="{ free: row.free }" :style="row.free ? undefined : { background: partColor(row.id) }" />
        <span class="label">{{ row.label }}</span>
        <span class="tokens">{{ compactNumber(row.tokens) }}</span>
        <strong class="percent">{{ formatPercent(row.percent) }}</strong>
      </li>
    </ul>
    </template>
    <div v-if="accuracy" class="accuracy" data-test="context-accuracy">
      <SegmentedControl v-model="choice" :options="CONTEXT_ACCURACY_OPTIONS" aria-label="Breakdown accuracy" />
      <span>Applies from your next question.</span>
    </div>
    <p v-if="window > 0 && parts.length" class="note" data-test="context-note">
      {{ exact ? "Counted by the model provider." : "Estimated from the prompt text." }}
      The total is what the model reported.
    </p>
    <section v-if="agentUsage?.length" class="agent-contexts" data-test="agent-contexts" aria-label="Prompt cost per agent">
      <h3>Prompt cost per agent</h3>
      <p class="note">Each call's prompt, counted separately from the answering agent's context window.</p>
      <section v-for="(agent, index) in agentUsage" :key="index" class="agent-context" data-test="agent-context">
        <h4>
          <span>{{ agent.agent_label || agent.agent }}</span>
          <span v-if="agent.context_breakdown?.length" class="count-kind">{{ agent.context_breakdown_exact ? "Exact" : "Estimated" }}</span>
        </h4>
        <ul v-if="agent.context_breakdown?.length" class="rows agent-rows">
          <li v-for="part in agent.context_breakdown" :key="part.id" :data-part="part.id">
            <i class="swatch" :style="{ background: partColor(part.id) }" />
            <span class="label">{{ part.label }}</span>
            <span class="tokens">{{ compactNumber(part.tokens) }}</span>
          </li>
        </ul>
        <p v-else class="note">Breakdown unavailable.</p>
      </section>
    </section>
  </div>
</template>

<style scoped>
.context-panel {
  --part-system_prompt: var(--accent);
  --part-agents: light-dark(#7048e8, #9775fa);
  --part-builtin_tools: light-dark(#2a78d6, #3987e5);
  --part-mcp_tools: light-dark(#1baf7a, #20c38a);
  --part-messages: light-dark(#d9a400, #f0b429);
  --part-other: var(--muted);
  box-sizing: border-box;
  width: min(320px, calc(100vw - 32px));
  max-height: 65vh;
  overflow-y: auto;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  color: var(--text);
  background: var(--surface);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.18);
  font-size: 0.9em;
}
.summary {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 8px;
}
.summary span {
  color: var(--muted);
}
.bar {
  display: flex;
  height: 8px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--code-bg);
}
.bar i {
  display: block;
  height: 100%;
}
.rows {
  display: grid;
  gap: 6px;
  margin: 12px 0 8px;
  padding: 0;
  list-style: none;
}
.rows li {
  display: grid;
  grid-template-columns: 12px 1fr auto 56px;
  align-items: center;
  gap: 8px;
}
.swatch {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-sm);
}
.swatch.free {
  border: 1px solid var(--border);
  background: transparent;
}
.tokens {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.percent {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.accuracy {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 0.8em;
  color: var(--muted);
}
.note {
  margin: 0;
  font-size: 0.8em;
  color: var(--muted);
}
.agent-contexts {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.agent-contexts h3 {
  margin: 0 0 6px;
  font-size: 1em;
  font-weight: 600;
}
.agent-context h4 {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 12px 0 6px;
  font-size: 0.9em;
  overflow-wrap: anywhere;
}
.count-kind {
  color: var(--muted);
  font-size: 0.85em;
  font-weight: 400;
}
.agent-rows li {
  grid-template-columns: 12px minmax(0, 1fr) auto;
  overflow-wrap: anywhere;
}
</style>
