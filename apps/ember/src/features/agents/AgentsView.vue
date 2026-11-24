<script setup lang="ts">
import PageLayout from "../../components/layout/PageLayout.vue";
import { computed, onMounted, ref } from "vue";
import { usePolling } from "../../composables/time/usePolling";
import { accountAgentsClient, agentsClient, type AgentListing } from "./api/AgentsClient";
import AgentCard from "./components/AgentCard.vue";
import AgentLlm from "./components/AgentLlm.vue";
import PanelHelp from "../../components/ui/panel/PanelHelp.vue";
import RecordDrawer from "../../components/ui/panel/RecordDrawer.vue";
import SearchField from "../../components/ui/lists/SearchField.vue";
import SegmentedControl from "../../components/ui/forms/SegmentedControl.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { errorMessage } from "../../utils/errors";
import { plural } from "../../utils/format";

/** Every agent behind ember, running or not (ember_api's GET /api/agents).
 * Read-only: new chats always go to the entry agent, which hands work to the
 * others itself; each account can switch a specialist off for its own chats.
 * Refreshed every 15 s while the page is open. */

const REFRESH_MS = 15_000;

const agents = ref<AgentListing[]>([]);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");
const disabled = ref<string[]>([]);
const pending = ref<string[]>([]);
const query = ref("");
const status = ref("all");
const statusOptions = [
  { value: "all", label: "All" }, { value: "running", label: "Running" },
  { value: "offline", label: "Offline" }, { value: "disabled", label: "Disabled" },
];
const openedId = ref<string | null>(null);
const opened = computed(() => agents.value.find(agent => agent.id === openedId.value));
const entryLabels = computed(() => agents.value.filter(agent => agent.entry).map(agent => agent.label).join(", "));
const hasRouter = computed(() => agents.value.some(agent => agent.internal_role === "router"));
const visible = computed(() => {
  const search = query.value.trim().toLowerCase();
  return agents.value.filter(agent => (status.value === "all" || agent.status === status.value)
    && [agent.label, agent.id, agent.focus, agent.provider, agent.gateway, agent.model,
      agent.architect ? "architect" : "", agent.architect?.kind, ...(agent.architect?.workers ?? []),
      ...agent.tiers.flatMap(tier => [tier.tier, tier.id, tier.use_for])].join(" ").toLowerCase().includes(search));
});
const groups = computed(() => [
  { id: "front", title: "The front of your conversation", note: hasRouter.value
    ? "The entry agent receives your message. The internal Router helps choose a specialist and model."
    : "The entry agent receives your message and brings in the right help.", agents: visible.value.filter(agent => agent.entry || agent.internal_role) },
  { id: "architects", title: "Architects", note: "Plan the work, then hand it to specialists.",
    agents: visible.value.filter(agent => agent.architect) },
  { id: "team", title: "The team behind your chats", note: "Orchestrators coordinate larger tasks. Specialists take focused work from the entry agent.", agents: [
    ...visible.value.filter(agent => !agent.entry && !agent.internal_role && !agent.architect && agent.orchestrator),
    ...visible.value.filter(agent => !agent.entry && !agent.internal_role && !agent.architect && !agent.orchestrator),
  ] },
]);
let preferenceRevision = 0;
// A switch stays pending until the server answers; the shown state is never unconfirmed.
async function toggle(agentId: string, enabled: boolean): Promise<void> {
  if (pending.value.includes(agentId)) return;
  preferenceRevision++;
  pending.value = [...pending.value, agentId];
  try {
    disabled.value = (await accountAgentsClient.set(agentId, enabled)).disabled;
    error.value = "";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    preferenceRevision++;
    pending.value = pending.value.filter((id) => id !== agentId);
  }
}

const summary = computed(() => {
  const count = (status: AgentListing["status"]) => agents.value.filter((a) => a.status === status).length;
  const parts = [`${count("running")} running`];
  if (count("offline")) parts.push(`${count("offline")} offline`);
  if (count("disabled")) parts.push(`${count("disabled")} disabled`);
  return parts.join(" · ");
});

async function refresh(): Promise<void> {
  if (refreshing.value) return;
  const revision = preferenceRevision;
  refreshing.value = true;
  try {
    const [listed, mine] = await Promise.all([agentsClient.list(), accountAgentsClient.get()]);
    agents.value = listed;
    // A background read must not undo a preference confirmed while it was in flight.
    if (revision === preferenceRevision && !pending.value.length) disabled.value = mine.disabled;
    error.value = "";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

usePolling(refresh, REFRESH_MS);
onMounted(() => void refresh());
</script>

<template>
  <PageLayout class="agents-view" title="Agents">
    <section class="roster" aria-label="Agent roster">
      <header class="roster-head">
        <div class="roster-title">
          <h3>Agent roster</h3>
          <p v-if="!loading && agents.length"><span class="summary">{{ summary }}</span> · {{ plural(visible.length, 'agent') }} shown · auto-refresh every 15 s</p>
        </div>
        <div class="roster-tools">
          <PanelHelp title="Agents">Meet the team behind your conversations. The entry agent brings in the right help. Switches apply only to your chats; service status is separate.</PanelHelp>
          <button type="button" class="admin-icon" aria-label="Refresh" title="Refresh" :disabled="refreshing" :aria-busy="refreshing" @click="refresh">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" /></svg>
          </button>
          <SearchField v-if="!loading && agents.length" v-model="query" class="roster-search" label="Search agents" placeholder="Search agent or model" />
        </div>
      </header>
      <div class="roster-body">
      <StateMessage v-if="error" kind="error" @retry="refresh">Could not update the agents: {{ error }}</StateMessage>
      <StateMessage v-if="loading" kind="loading">Loading agents…</StateMessage>
      <StateMessage v-else-if="!agents.length && !error" kind="empty">No agents are running or defined.</StateMessage>
      <template v-if="!loading && agents.length">
      <div class="handoff" aria-label="How work is handed off">
        <span class="call-chip">You</span><span aria-hidden="true">→</span>
        <strong>{{ entryLabels || 'Entry agent' }} <span class="muted">/ Entry</span></strong>
        <template v-if="hasRouter"><span aria-hidden="true">→</span><span>Router recommends</span></template>
        <span aria-hidden="true">→</span><span>Orchestrators & specialists</span>
      </div>
      <p class="account-note">New chats always start with the entry agent. Specialist switches apply only to your chats; service status is separate.</p>
      <div class="filters">
        <SegmentedControl v-model="status" :options="statusOptions" aria-label="Filter by service status" />
      </div>
      <StateMessage v-if="!visible.length" kind="empty" title="No matching agents">
        Try another name, model or service status.
        <template #action><button type="button" class="pill-btn ghost" @click="query = ''; status = 'all'">Clear filters</button></template>
      </StateMessage>
      <section v-for="group in groups.filter(group => group.agents.length)" :key="group.id" class="agent-group" :aria-labelledby="`agents-${group.id}`">
        <h3 :id="`agents-${group.id}`">{{ group.title }}</h3><p class="group-note">{{ group.note }}</p>
        <div class="grid" :class="{ 'front-grid': group.id === 'front' }">
          <AgentCard
            v-for="agent in group.agents"
            :key="agent.id"
            :agent="agent"
            :off="disabled.includes(agent.id)"
            :pending="pending.includes(agent.id)"
            @toggle="toggle"
            @open="openedId = $event"
          />
        </div>
      </section>
      </template>
      </div>
    </section>
  </PageLayout>
  <RecordDrawer :open="!!opened" :title="opened?.label ?? 'Agent description'" @close="openedId = null">
    <template v-if="opened">
      <code class="agent-id">{{ opened.id }}</code>
      <p class="full-description">{{ opened.focus || 'No description.' }}</p>
      <AgentLlm :agent="opened" />
      <p v-if="opened.internal_role === 'router'" class="full-description">
        Laya English → typed-decisions<span v-if="opened.decision?.fallback"> → Jev fallback</span>.
        <template v-if="opened.decision?.fallback_available === false">Fallback unavailable.</template>
        <template v-if="opened.decision?.local_status === 'not_loaded'">Local models load on first use.</template>
        <template v-if="opened.decision?.local_status === 'unavailable'">Local models unavailable.</template>
        Internal routing; answers come from the selected agent.
      </p>
    </template>
  </RecordDrawer>
</template>

<style scoped>
.handoff, .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.muted, .account-note, .group-note { color: var(--muted); }
/* One roster panel, as in the admin apps: a header with the title and search, then the body. */
.roster { overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.roster-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg); }
.roster-title h3 { margin: 0; font-size: 1em; font-weight: 600; }
.roster-title p { margin: 2px 0 0; font-size: .8em; color: var(--muted); }
.roster-tools { display: flex; align-items: center; gap: 8px; min-width: 0; }
.roster-search { flex: 0 1 260px; min-width: 160px; }
.roster-body { padding: 16px; }
.handoff { padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); font-size: .85em; }
.handoff strong { color: var(--accent); }
.account-note { font-size: .85em; margin: 8px 0 16px; }
.filters { margin-bottom: 16px; }
.agent-group + .agent-group { margin-top: 32px; }
.agent-group h3 { margin: 0; font-size: 1em; font-weight: 600; }
.group-note { margin: 4px 0 12px; font-size: .85em; }
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.front-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.agent-id { font: .8em var(--mono); color: var(--muted); overflow-wrap: anywhere; }
.full-description { overflow-wrap: anywhere; }
.agents-view :deep(button), .done { min-width: 44px; min-height: 44px; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (min-width: 768px) and (max-width: 900px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) {
  .grid { grid-template-columns: minmax(0, 1fr); }
  .roster-search { flex-basis: 100%; }
  .filters :deep(.segment) { padding-inline: 8px; }
}
</style>
