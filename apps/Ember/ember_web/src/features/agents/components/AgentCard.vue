<script setup lang="ts">
import type { AgentListing, AgentStatus } from "../api/AgentsClient";
import AgentLlm from "./AgentLlm.vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";

/** One agent on the Agents page: name, id, role badges, what it is for, its
 * provider / gateway / model, and whether it is running. The card opens a dialog with the full description. The status is an icon and a word, never colour alone. */
const props = defineProps<{ agent: AgentListing; off?: boolean; pending?: boolean }>();
const emit = defineEmits<{ toggle: [agentId: string, enabled: boolean]; open: [agentId: string] }>();

function requestToggle(event: Event): void {
  const input = event.target as HTMLInputElement;
  const enabled = input.checked;
  // The native input changes before Vue's handler: keep showing the confirmed value.
  input.checked = !props.off;
  if (!props.pending) emit("toggle", props.agent.id, enabled);
}

const STATUS_TEXT: Record<AgentStatus, string> = { running: "Running", offline: "Offline", disabled: "Disabled" };
const STATUS_ICON: Record<AgentStatus, string> = { running: "●", offline: "○", disabled: "–" };
</script>

<template>
  <article :class="['agent-card', agent.status, { entry: agent.entry, front: agent.entry || agent.internal_role, off }]" :aria-busy="!!pending">
    <div class="card-content">
      <span class="head">
        <span class="icon-tile" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 4H5a1 1 0 0 0-1 1v3m12-4h3a1 1 0 0 1 1 1v3M4 16v3a1 1 0 0 0 1 1h3m12-4v3a1 1 0 0 1-1 1h-3M8 12h8m-4-4v8" /></svg></span>
        <span class="identity"><h3><button type="button" class="open-card" aria-haspopup="dialog" :aria-label="`Open ${agent.label}`" @click="$emit('open', agent.id)">{{ agent.label }}</button></h3><code class="agent-id">{{ agent.id }}</code></span>
        <span class="status status-badge"><span aria-hidden="true">{{ STATUS_ICON[agent.status] }}</span> {{ STATUS_TEXT[agent.status] }}</span>
      </span>
      <span class="roles">
        <span v-if="agent.entry || agent.orchestrator || agent.internal_role || agent.architect" class="tags">
          <span v-if="agent.internal_role === 'router'" class="tag call-chip">Internal / Router</span>
          <span v-if="agent.architect" class="tag call-chip">Architect · {{ agent.architect.kind }}</span>
          <span v-if="agent.entry" class="tag call-chip">Entry</span>
          <span v-if="agent.orchestrator" class="tag call-chip">Orchestrator</span>
        </span>
        <span v-else class="call-chip">Specialist</span>
      </span>
      <span class="focus">{{ agent.focus || "No description." }}</span>
      <span v-if="agent.architect?.workers.length" class="architect-workers">Builds with: {{ agent.architect.workers.join(", ") }}</span>
      <AgentLlm :agent="agent" />
      <span v-if="agent.internal_role === 'router'" class="decision-chain">
      Laya English → typed-decisions<span v-if="agent.decision?.fallback"> → Jev fallback</span>.
      <span v-if="agent.decision?.fallback_available === false" class="fallback"><span aria-hidden="true">△</span> Fallback unavailable.</span>
      <template v-if="agent.decision?.local_status === 'not_loaded'">Local models load on first use.</template>
      <template v-if="agent.decision?.local_status === 'unavailable'">Local models unavailable.</template>
      Internal routing; answers come from the selected agent.
      </span>
    </div>
    <div class="agent-controls">
    <ToggleSwitch
      v-if="!agent.entry && !agent.orchestrator && !agent.internal_role && !agent.architect"
      :aria-label="`Use ${agent.label}`"
      :checked="!off"
      :disabled="pending"
      :aria-busy="!!pending"
      title="Let Ember hand work to this agent in your chats."
      @change="requestToggle"
    >{{ pending ? "Saving…" : off ? "Off for your chats" : "On for your chats" }}</ToggleSwitch>
    <span v-else class="managed">{{ agent.architect ? 'Used by the orchestrator in plan mode' : agent.entry ? 'Every new chat starts here' : agent.internal_role ? 'Internal · does not answer chats' : 'Available to the entry agent' }}</span>
    </div>
  </article>
</template>

<style scoped>
.agent-card {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.agent-card :deep(.toggle) { min-height: 44px; }
.agent-card.front {
  border-color: var(--accent);
}
.card-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  padding: 12px;
  gap: 8px;
  border-radius: var(--radius-lg);
}
.open-card { padding: 0; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.open-card::after { content: ""; position: absolute; inset: 0; border-radius: var(--radius-lg); }
.open-card:focus-visible { outline: none; }
.open-card:focus-visible::after {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.agent-card:hover {
  border-color: var(--accent);
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.identity { display: flex; flex: 1; flex-direction: column; min-width: 0; overflow-wrap: anywhere; }
.icon-tile { display: grid; place-items: center; flex: none; width: 34px; height: 34px; border-radius: var(--radius-md); background: var(--bg); color: var(--accent); }
.icon-tile svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
h3 {
  margin: 0;
  font-size: 1em;
  font-weight: 600;
  color: var(--text);
}
.status {
  flex-shrink: 0;
  font-size: 0.8em;
  color: var(--text);
  background: var(--bg);
}
.agent-id {
  font-family: var(--mono);
  font-size: 0.8em;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.roles { display: flex; min-height: 1.55em; }
.roles .call-chip {
  margin-left: 0;
}
.focus {
  width: 100%;
  font-size: 0.9em;
  color: var(--muted);
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}
.card-content :deep(.llm) { width: 100%; }
.architect-workers { font-size: .85em; color: var(--muted); overflow-wrap: anywhere; }
.decision-chain { font-size: .85em; overflow-wrap: anywhere; }
.fallback { display: block; color: var(--warning); }
.agent-controls { position: relative; z-index: 1; display: flex; align-items: center; min-height: 60px; margin-top: auto; padding: 8px 12px; border-top: 1px solid var(--border); }
.managed { font-size: .8em; color: var(--muted); }
</style>
