<script setup lang="ts">
import { computed } from "vue";
import type { LogEntry } from "../api/LogsClient";
import { agentRuns } from "../utils/chatTrace";

/** What a chat-turn log entry adds below its line: every agent that ran. Normal
 * lists each with its model and tokens and keeps the raw Details; Advanced shows
 * each agent's run (delegation, timing, tools) and the prompt it received.
 * System prompts are never stored, so they never show. */
const props = defineProps<{ entry: LogEntry; advanced: boolean }>();

const runs = computed(() => agentRuns(props.entry.details, props.entry.prompts));

function tokens(n: number | undefined): string {
  return n === undefined ? "?" : n.toLocaleString();
}
</script>

<template>
  <ul v-if="!advanced && runs.length" class="agents">
    <li v-for="(run, i) in runs" :key="i">
      <span class="name">{{ run.agent.agent_label ?? run.agent.agent_id }}</span>
      <code v-if="run.agent.model" class="model">{{ run.agent.model }}</code>
      <span class="muted">{{ tokens(run.agent.total_tokens) }} tokens</span>
    </li>
  </ul>
  <details v-if="!advanced && entry.details">
    <summary>Details</summary>
    <pre>{{ entry.details }}</pre>
  </details>

  <div v-if="advanced" class="runs">
    <p v-if="!runs.length" class="muted">No per-agent data: this entry was logged before agents were recorded.</p>
    <section v-for="(run, i) in runs" :key="i" class="run" :aria-label="`Agent ${run.agent.agent_id}`">
      <div class="head">
        <strong>{{ run.agent.agent_label ?? run.agent.agent_id }}</strong>
        <code class="muted">{{ run.agent.agent_id }}</code>
        <span v-if="run.agent.delegated_by" class="muted">delegated by {{ run.agent.delegated_by }}</span>
        <span v-else class="muted">answered the question</span>
      </div>
      <div class="chips">
        <span v-if="run.agent.provider_id" class="chip">{{ run.agent.provider_id }}</span>
        <span v-if="run.agent.gateway" class="chip">{{ run.agent.gateway }}</span>
        <span v-if="run.agent.model" class="chip">{{ run.agent.model }}</span>
        <span v-if="run.agent.model_tier" class="chip">tier {{ run.agent.model_tier }}</span>
        <span v-if="run.agent.reasoning_effort" class="chip">effort {{ run.agent.reasoning_effort }}</span>
      </div>
      <p class="muted facts">
        {{ tokens(run.agent.input_tokens) }} in<template v-if="run.agent.cached_input_tokens"> ({{ tokens(run.agent.cached_input_tokens) }} cached)</template> · {{ tokens(run.agent.output_tokens) }} out · {{ tokens(run.agent.total_tokens) }} total
        <template v-if="run.seconds !== null"> · {{ run.seconds }}s</template>
      </p>
      <p v-if="run.agent.tools.length" class="muted facts">Tools: {{ run.agent.tools.join(", ") }}</p>

      <details v-if="run.prompt" class="prompt">
        <summary>
          Prompt ({{ run.prompt.messages.length }} message{{ run.prompt.messages.length === 1 ? "" : "s" }})<template v-if="run.prompt.truncated"> · shortened</template>
        </summary>
        <div v-for="(message, j) in run.prompt.messages" :key="j" class="message-box">
          <span class="role">{{ message.role }}</span>
          <pre>{{ message.content }}</pre>
        </div>
        <p class="muted facts">The system prompt is not recorded.</p>
      </details>
      <p v-else class="muted facts">No prompt recorded.</p>
    </section>
  </div>
</template>

<style scoped>
.agents {
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 2px 16px;
  font-size: 0.85em;
}
.agents li {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.name {
  font-weight: 500;
}
.model {
  font-family: var(--mono);
  font-size: 0.85em;
  color: var(--muted);
}
.muted {
  color: var(--muted);
}
details summary {
  cursor: pointer;
  font-size: 0.85em;
  color: var(--muted);
}
.runs {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
.run {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  min-width: 0;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 10px;
}
.head code {
  font-family: var(--mono);
  font-size: 0.85em;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.chip {
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 0.8em;
  color: var(--muted);
  background: var(--code-bg);
}
.facts {
  margin: 6px 0 0;
  font-size: 0.8em;
}
.prompt {
  margin-top: 8px;
}
.message-box {
  margin-top: 6px;
}
.role {
  font-size: 0.75em;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}
pre {
  margin: 2px 0 0;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: var(--code-bg);
  font-family: var(--mono);
  font-size: 0.85em;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
