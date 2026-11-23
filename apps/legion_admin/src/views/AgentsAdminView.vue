<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AdminSearch from "../components/admin/AdminSearch.vue";
import StatusFilters from "../components/admin/StatusFilters.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import {
  agentsAdminClient,
  type AgentConfig,
  type AgentFile,
  type AgentStatus,
  type LiveAgent,
  type ProviderCatalog,
} from "../api/AgentsAdminClient";
import { capabilitiesAdminClient } from "../api/CapabilitiesAdminClient";
import type { CapabilityInfo } from "../api/CommandsClient";
import AgentAdminCard from "../components/admin/AgentAdminCard.vue";
import AgentForm from "../components/admin/AgentForm.vue";
import SharedPromptsDrawer from "../components/admin/SharedPromptsDrawer.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import { errorMessage } from "../utils/errors";

// ai_agent's supervisor rescans its agents folder about every 2 seconds.
const SETTLE_MS = 3000;

const agents = ref<AgentFile[]>([]);
const providers = ref<ProviderCatalog>({});
const capabilities = ref<CapabilityInfo[]>([]);
const live = ref<Record<string, LiveAgent>>({});
const loading = ref(true);
const error = ref("");
const notice = ref("");

const route = useRoute();
const router = useRouter();
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const selectedId = ref<string>();
const creating = ref(false);
const editing = ref(false);
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const pending = ref<{ id: string; config: AgentConfig }>();
const selected = computed(() => agents.value.find((agent) => agent.id === selectedId.value));
const drawerOpen = computed(() => !!selected.value || creating.value);
const statuses = {
  running: "Running",
  offline: "Offline",
  disabled: "Disabled",
  unknown: "Unknown",
} satisfies Record<AgentStatus | "unknown", string>;
type Status = keyof typeof statuses;
type Filter = Status | "all";
const localFilter = ref<Filter>("all");
const filter = computed(() => route.query.status === "offline" ? "offline" : localFilter.value);
const filters = [
  { id: "all", label: "All agents", tone: "accent" },
  { id: "running", label: "Running", tone: "success" },
  { id: "offline", label: "Offline", tone: "warning" },
  { id: "disabled", label: "Disabled", tone: "muted" },
  { id: "unknown", label: "Unknown", tone: "muted" },
] as const;

function setFilter(next: Filter) {
  localFilter.value = next;
  if (next === "offline" || route.query.status === "offline") {
    void router.replace({ query: { ...route.query, status: next === "offline" ? next : undefined } });
  }
}

function role(agent: AgentFile) {
  return agent.role === "orchestrator" ? "Orchestrator" : agent.role === "router" ? "Internal router" : "Specialist";
}

const roster = computed(() => agents.value.map((agent) => ({
  agent,
  status: (agent.enabled === false ? "disabled" : live.value[agent.id]?.status ?? "unknown") as Status,
  role: role(agent),
})));
const totals = computed(() => {
  const counts = { all: roster.value.length, running: 0, offline: 0, disabled: 0, unknown: 0 };
  for (const row of roster.value) counts[row.status]++;
  return counts;
});
const filterOptions = computed(() => filters.map((item) => ({ ...item, count: totals.value[item.id] })));
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return roster.value.filter(({ agent, status, role }) =>
    (filter.value === "all" || status === filter.value) &&
    [agent.label, agent.id, agent.focus, role, statuses[status]].some((value) => value?.toLowerCase().includes(query)));
});
const saving = ref(false);
const formError = ref("");

const previewText = ref("");
const previewing = ref(false);
const previewError = ref("");
const promptsOpen = ref(false);

const removing = ref<AgentFile | null>(null);
const removeBusy = ref(false);
const removeError = ref("");

const resetting = ref<AgentFile | null>(null);
const resetBusy = ref(false);
const resetError = ref("");

let settleTimer: ReturnType<typeof setTimeout> | undefined;
let statusRequest = 0;

const suggestedPort = computed(() => Math.max(29603, ...agents.value.map((a) => a.port ?? 0)) + 1);

async function loadStatuses(): Promise<void> {
  const request = ++statusRequest;
  try {
    const current = await agentsAdminClient.live();
    if (request === statusRequest) live.value = current;
  } catch {
    if (request === statusRequest) live.value = {};
  }
}

async function load(): Promise<void> {
  try {
    const [files, catalog] = await Promise.all([agentsAdminClient.list(), agentsAdminClient.gateways()]);
    agents.value = files;
    providers.value = catalog;
    error.value = "";
    // Needs capabilities.manage; without it the picker is empty and the text fields still work.
    capabilities.value = await capabilitiesAdminClient.list().catch(() => []);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
  await loadStatuses();
}

function settleSoon(message: string): void {
  notice.value = message;
  clearTimeout(settleTimer);
  settleTimer = setTimeout(() => {
    void loadStatuses();
    notice.value = "";
  }, SETTLE_MS);
}

async function preview(id: string, config: AgentConfig, caveman: boolean): Promise<void> {
  previewing.value = true;
  previewError.value = "";
  try {
    previewText.value = await agentsAdminClient.previewPrompt(id, config, caveman);
  } catch (err) {
    previewText.value = "";
    previewError.value = errorMessage(err);
  } finally {
    previewing.value = false;
  }
}

function resetPreview(): void {
  previewText.value = "";
  previewError.value = "";
}

function openCreate(): void {
  resetPreview();
  selectedId.value = undefined;
  creating.value = editing.value = true;
  formError.value = "";
}

function openEdit(): void {
  resetPreview();
  formError.value = "";
  editing.value = true;
}

function closeDetails(): void {
  selectedId.value = undefined;
  creating.value = editing.value = false;
  pending.value = undefined;
}

function discard(): void {
  pending.value = undefined;
  if (creating.value) closeDetails();
  else editing.value = false;
}

function requestSave(id: string, config: AgentConfig): void {
  pending.value = { id, config };
  drawer.value?.requestSave();
}

async function save(): Promise<void> {
  if (!pending.value || saving.value) return;
  const { id, config } = pending.value;
  saving.value = true;
  formError.value = "";
  const isNew = creating.value;
  try {
    const saved = await (isNew ? agentsAdminClient.create(id, config) : agentsAdminClient.update(id, config));
    agents.value = [...agents.value.filter((agent) => agent.id !== id), saved].sort((a, b) => a.id.localeCompare(b.id));
    agents.value = await agentsAdminClient.list().catch(() => agents.value);
    selectedId.value = id;
    creating.value = editing.value = false;
    pending.value = undefined;
    settleSoon(isNew ? `Created ${id}. It starts in a few seconds.` : `Saved ${id}. It restarts in a few seconds.`);
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

async function confirmRemove(): Promise<void> {
  const target = removing.value;
  if (!target) return;
  removeBusy.value = true;
  removeError.value = "";
  try {
    await agentsAdminClient.remove(target.id);
    agents.value = agents.value.filter((a) => a.id !== target.id);
    removing.value = null;
    closeDetails();
    settleSoon(`Removed ${target.id}. It stops in a few seconds.`);
  } catch (err) {
    removeError.value = errorMessage(err);
  } finally {
    removeBusy.value = false;
  }
}

async function confirmReset(): Promise<void> {
  const target = resetting.value;
  if (!target) return;
  resetBusy.value = true;
  resetError.value = "";
  try {
    const saved = await agentsAdminClient.reset(target.id);
    agents.value = agents.value.map((agent) => agent.id === target.id ? saved : agent);
    resetting.value = null;
    settleSoon(`Reset ${target.id} to its defaults. It restarts in a few seconds.`);
  } catch (err) {
    resetError.value = errorMessage(err);
  } finally {
    resetBusy.value = false;
  }
}

onMounted(load);
onBeforeUnmount(() => clearTimeout(settleTimer));
</script>

<template>
  <PageLayout class="agents-admin" title="Agents" wide>
    <StatusFilters :model-value="filter" label="Filter agents" :options="filterOptions" @update:model-value="setFilter" />
    <p v-if="notice" class="notice" role="status" data-test="notice">{{ notice }}</p>
    <section class="admin-panel-card" aria-labelledby="agent-roster">
      <header class="admin-panel-head">
        <h2 id="agent-roster">Agent roster</h2>
        <div class="admin-panel-tools">
          <button type="button" class="chip" data-test="shared-prompts" @click="promptsOpen = true">Shared prompts</button>
          <button type="button" class="primary" data-test="new" :disabled="loading || !!error" @click="openCreate">New agent</button>
          <AdminSearch ref="searchField" v-model="search" label="Search agents" />
        </div>
      </header>
      <p v-if="error" class="admin-panel-text error" role="alert">{{ error }}</p>
      <p v-else-if="loading" class="admin-panel-text muted" role="status">Loading agents…</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">{{ agents.length ? 'No agents match these filters.' : 'No agents are defined.' }}
        <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button>
      </p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="agent-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">Agent</th><th scope="col">Role</th><th scope="col">State</th></tr></thead>
          <tbody>
            <tr v-for="{ agent, status, role } in visible" :key="agent.id" :data-id="agent.id" data-test="agent">
              <th scope="row">
                <div class="admin-record-name">
                  <span class="admin-record-badge" aria-hidden="true">{{ (agent.label || agent.id).slice(0, 2).toUpperCase() }}</span>
                  <div><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="selectedId = agent.id">{{ agent.label || agent.id }}</button><code>{{ agent.id }}</code></div>
                </div>
              </th>
              <td>{{ role }}</td>
              <td><span class="agent-state" :class="status" data-test="status"><span aria-hidden="true">●</span> {{ statuses[status] }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!loading && !error" class="admin-panel-text muted count" role="status">{{ visible.length }} of {{ agents.length }} agents</p>
    </section>
    <RecordDrawer ref="drawer" :open="drawerOpen" :title="creating ? 'New agent' : 'Agent details'"
      :editable="!!selected && !selected.error" :editing="editing" :busy="saving" :fallback-focus="() => searchField?.focus()" :save-label="creating ? 'Create agent' : undefined"
      @edit="openEdit" @close="closeDetails" @discard="discard" @save="save">
      <AgentForm v-if="editing" :open="true" :initial="selected ?? null" :providers="providers" :capabilities="capabilities"
        :suggested-port="suggestedPort" :busy="saving" :error="formError" :preview-text="previewText" :previewing="previewing"
        :preview-error="previewError" @save="requestSave" @preview="preview" />
      <AgentAdminCard v-else-if="selected" :agent="selected" :status="live[selected.id]?.status" :tiers="live[selected.id]?.tiers"
        :decision="live[selected.id]?.decision" @remove="removing = selected; removeError = ''" @reset="resetting = selected; resetError = ''" />
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="saving" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="submit" form="agent-editor" class="primary" :disabled="saving" :aria-busy="saving">{{ creating ? 'Create agent' : 'Save changes' }}</button>
      </template>
    </RecordDrawer>
    <SharedPromptsDrawer :open="promptsOpen" @close="promptsOpen = false" @saved="settleSoon('Shared prompts saved. Every agent restarts in a few seconds.')" />
    <ConfirmModal
      :open="resetting !== null"
      title="Reset agent"
      :message="resetError || `Reset ${resetting?.label || resetting?.id || ''} to its defaults? Every change made here (model, tier limits, enabled, persona...) is discarded and the tracked file in agents/ applies again.`"
      confirm-label="Reset to defaults"
      :busy="resetBusy"
      @confirm="confirmReset"
      @close="resetting = null"
    />
    <ConfirmModal
      :open="removing !== null"
      title="Remove agent"
      :message="removeError || `Remove ${removing?.label || removing?.id || ''}? Its file is deleted and the agent stops. Other agents that delegate to it will find it gone.`"
      confirm-label="Remove"
      danger
      :require-text="removing?.id ?? ''"
      :busy="removeBusy"
      @confirm="confirmRemove"
      @close="removing = null"
    />

  </PageLayout>
</template>

<style scoped>
.agent-state { display: inline-flex; gap: 5px; align-items: center; padding: 3px 8px; border-radius: var(--radius-full); color: var(--muted); background: var(--surface); font-size: 0.8rem; }
.agent-state.running { color: var(--text); background: color-mix(in srgb, var(--success) 12%, var(--bg)); }
.agent-state.offline { color: var(--text); background: color-mix(in srgb, var(--warning) 14%, var(--bg)); }
.agent-state.running span { color: var(--success); }
.agent-state.offline span { color: var(--warning); }
.count { border-top: 1px solid var(--border); font-size: 0.8rem; }
.notice { color: var(--muted); }
@media (max-width: 400px) { .admin-record-badge { display: none; } }
</style>
