<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { computed, onMounted, ref, watch } from "vue";
import { capabilitiesAdminClient, type CapabilityStatus } from "../api/CapabilitiesAdminClient";
import { commandsClient } from "../api/CommandsClient";
import { AdminSearch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { StatusFilters } from "@citadel/ui";
import CapabilityDrawer from "../components/CapabilityDrawer.vue";
import { ToggleSwitch } from "@citadel/ui";
import { useNoticesStore } from "../stores/notices";
import { errorMessage } from "../utils/errors";
import "@citadel/ui/admin.css";

const notices = useNoticesStore();
const capabilities = ref<CapabilityStatus[]>([]);
const query = ref("");
const filter = ref<"all" | "online" | "offline">("all");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const selectedName = ref<string | null>(null);
const selected = computed(() => capabilities.value.find((c) => c.name === selectedName.value) ?? null);
const summaries = ref<Record<string, string>>({});
let summariesRequest: Promise<void> | null = null;
watch(selectedName, (name) => {
  if (!name || summariesRequest) return;
  summariesRequest = commandsClient.helpIndex().then((index) => {
    if (!index || typeof index !== "object" || !("capabilities" in index) || !Array.isArray(index.capabilities)) return;
    for (const row of index.capabilities) {
      if (row && typeof row.capability === "string" && typeof row.summary === "string" && row.summary.trim()) {
        summaries.value[row.capability.replace(/^\//, "")] = row.summary.trim();
      }
    }
  }).catch(() => { /* The fallback remains visible if help metadata is unavailable. */ })
    .finally(() => { summariesRequest = null; });
});
const loading = ref(true);
const error = ref("");
const refreshing = ref(false);
// A switch waits for the server's answer: the name is here while its call is in flight.
const pending = ref<Set<string>>(new Set());
const rowErrors = ref<Record<string, string>>({});

type State = "online" | "offline" | "new" | "error" | "missing";

function stateOf(c: CapabilityStatus): State {
  if (c.missing) return "missing";
  if (c.enabled) return "online";
  if (c.load_error) return "error";
  if (!c.loaded) return "new";
  return "offline";
}

const STATE_LABELS: Record<State, string> = {
  online: "Online",
  offline: "Offline",
  new: "New, offline",
  error: "Failed to load",
  missing: "Folder missing",
};

/** What each state means and what to do about it, shown in the helper popover beside the state. */
const STATE_HELP: Record<State, string> = {
  online: "The capability is loaded and its tools can be used. Nothing to do. Use Restart to load its code from disk again.",
  offline: "The capability is switched off, so its tools are not offered. Turn Online on to start it.",
  new: "Armory found this capability but has never loaded it. Turn Online on to load it and see its tools.",
  error: "Its code failed to load, so it stays offline. Read the error under its name, fix the code, then turn Online on or use Restart.",
  missing: "The capability's folder is gone from disk. Restore the folder, or remove the capability from the configuration.",
};

const rows = computed(() => {
  const search = query.value.trim().toLowerCase();
  return capabilities.value
    .filter((c) => filter.value === "all" || (filter.value === "online") === c.enabled)
    .filter((c) => `${c.name} ${c.label ?? ""} ${c.tools.join(" ")}`.toLowerCase().includes(search))
    .map((c) => ({ c, state: stateOf(c) }));
});
const options = computed(() => [
  { id: "all" as const, label: "All", count: capabilities.value.length },
  { id: "online" as const, label: "Online", count: capabilities.value.filter((c) => c.enabled).length, tone: "success" as const },
  { id: "offline" as const, label: "Offline", count: capabilities.value.filter((c) => !c.enabled).length, tone: "muted" as const },
]);

async function load(): Promise<void> {
  try {
    capabilities.value = await capabilitiesAdminClient.list();
    error.value = "";
    notices.report(true);
  } catch (err) {
    error.value = errorMessage(err);
    notices.report(false);
  } finally {
    loading.value = false;
  }
}

async function refresh(): Promise<void> {
  refreshing.value = true;
  try {
    capabilities.value = await capabilitiesAdminClient.refresh();
    error.value = "";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    refreshing.value = false;
  }
}

async function setOnline(c: CapabilityStatus, online: boolean): Promise<void> {
  pending.value = new Set(pending.value).add(c.name);
  delete rowErrors.value[c.name];
  try {
    const updated = await capabilitiesAdminClient.setOnline(c.name, online);
    capabilities.value = capabilities.value.map((x) => (x.name === c.name ? updated : x));
  } catch (err) {
    rowErrors.value[c.name] = errorMessage(err);
    // The server rolled back; read the real state (and its load_error) again.
    await load();
  } finally {
    const next = new Set(pending.value);
    next.delete(c.name);
    pending.value = next;
  }
}

// The checkbox flips natively on click; put it back so only the server's answer moves it.
function onToggle(c: CapabilityStatus, event: Event): void {
  const input = event.target as HTMLInputElement;
  const wanted = input.checked;
  input.checked = c.enabled;
  void setOnline(c, wanted);
}

onMounted(load);
</script>

<template>
  <PageLayout class="admin-panel" title="Capabilities" wide>
    <StatusFilters v-if="!loading" v-model="filter" label="Filter capabilities" :options="options" />
    <section class="admin-panel-card" aria-labelledby="capability-roster">
      <header class="admin-panel-head">
        <h2 id="capability-roster">Capabilities</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Capabilities">
            <p>Offline hides a capability's tools from every client. Going online, or Restart on an online one, loads its code from disk again.</p>
            <p>Refresh finds capability folders added while mcp_server runs; they start offline. Open a row to see its tools.</p>
          </PanelHelp>
          <button type="button" class="admin-icon" data-test="refresh" title="Refresh" aria-label="Refresh" :disabled="refreshing" :aria-busy="refreshing" @click="refresh">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" /></svg>
          </button>
          <AdminSearch ref="searchField" v-model="query" label="Search capabilities" />
        </div>
      </header>
      <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />
      <p v-if="loading" class="admin-panel-text muted" role="status">Loading…</p>
      <p v-else-if="!rows.length" class="admin-panel-text muted">{{ capabilities.length ? "No capabilities match your search." : "No capabilities are available." }} <button v-if="query || filter !== 'all'" type="button" class="chip" @click="query = ''; filter = 'all'; searchField?.focus()">Clear filters</button></p>
      <div v-else class="admin-table-scroll" role="region" aria-labelledby="capability-roster" tabindex="0">
        <table class="admin-records">
          <thead><tr><th scope="col">Capability</th><th scope="col">Status</th><th scope="col">Tools</th><th scope="col">Online</th></tr></thead>
          <tbody>
            <tr v-for="{ c, state } in rows" :key="c.name" data-test="capability" :data-name="c.name" :data-state="state">
              <th scope="row">
                <div class="admin-record-name">
                  <div>
                    <button type="button" class="admin-row-button" aria-haspopup="dialog" :aria-label="`Open ${c.label ?? c.name}`" @click="selectedName = c.name">{{ c.label ?? c.name }}</button>
                    <code>{{ c.name }}</code>
                  </div>
                </div>
                <pre v-if="c.load_error" class="load-error" data-test="load-error">{{ c.load_error }}</pre>
                <ActionMessage v-if="rowErrors[c.name]" kind="error" :text="rowErrors[c.name]" data-test="row-error" />
              </th>
              <td><div class="state-cell"><span class="state" :class="state"><span aria-hidden="true">{{ state === "online" ? "●" : "○" }}</span> {{ STATE_LABELS[state] }}</span>
                <PanelHelp v-if="state !== 'online'" :title="STATE_LABELS[state]"><p>{{ STATE_HELP[state] }}</p></PanelHelp></div></td>
              <td>{{ c.tools.length }}<template v-if="!c.loaded"> · not loaded yet</template></td>
              <td>
                <div class="controls">
                  <button v-if="c.enabled && !c.missing" type="button" class="admin-icon restart" data-test="restart" :disabled="pending.has(c.name)" :aria-label="`Restart ${c.label ?? c.name}`" title="Restart: load its code from disk again" @click="setOnline(c, true)">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" /></svg>
                  </button>
                  <ToggleSwitch :checked="c.enabled" :disabled="pending.has(c.name) || (c.missing && !c.enabled)" :aria-label="`${c.label ?? c.name} online`" @change="onToggle(c, $event)" />
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <CapabilityDrawer kind="capability" :status="selected ? STATE_LABELS[stateOf(selected)] : ''" :open="selected !== null" :title="selected?.label ?? selected?.name ?? ''" :identity="selected?.name ?? ''" :names="selected?.tools ?? []" :available="selected?.enabled ?? false" @close="selectedName = null">
      <template v-if="selected"><p>{{ summaries[selected.name] ?? `Workspace tools provided by ${selected.label ?? selected.name}. Select a tool below to explore what it does.` }}</p><pre v-if="selected.load_error" class="load-error">{{ selected.load_error }}</pre></template>
    </CapabilityDrawer>
  </PageLayout>
</template>

<style scoped>
.admin-records :is(th, td):first-child { width: 40%; }
.controls { position: relative; z-index: 1; display: flex; align-items: center; gap: 10px; }
.controls .restart { border: 1px solid var(--border); }
.restart:disabled svg { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.state-cell { display: flex; align-items: center; gap: 4px; }
.state { padding: 1px 8px; border-radius: var(--radius-sm); font-size: 0.8em; background: var(--surface); white-space: nowrap; }
.state.online { color: var(--success); }
.state.error, .state.missing { color: var(--danger); }
.load-error { margin: 8px 0 0; padding: 8px 10px; max-height: 4.5em; overflow: auto; scrollbar-gutter: stable; border-radius: var(--radius-md); background: var(--code-bg); font: 0.8em/1.4 var(--mono); font-weight: 400; white-space: pre-wrap; overflow-wrap: anywhere; }
.error { margin: 6px 0 0; color: var(--danger); font-weight: 400; }
.muted { color: var(--muted); }
</style>
