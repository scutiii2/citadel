<script setup lang="ts">
import ActionMessage from "../components/admin/ActionMessage.vue";
import { computed, onMounted, ref, watch } from "vue";
import { toolServicesClient, type ToolSaveBody, type ToolService, type ToolTestResult } from "../api/ToolServicesClient";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import FormTabs from "../components/admin/FormTabs.vue";
import StatusFilters from "../components/admin/StatusFilters.vue";
import TestResultCells from "../components/TestResultCells.vue";
import PageLayout from "../components/PageLayout.vue";
import PasswordInput from "../components/PasswordInput.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

interface AddressRow {
  key: number;
  address: string;
  name: string;
  found: boolean | null;
  hasOverride: boolean;
  token: string;
  lookup: number;
  checking: boolean;
  error: string;
}

interface Draft {
  saved: ToolService;
  enabled: boolean;
  token: string;
  addresses: AddressRow[];
  pending: "save" | "test" | "clear" | null;
  error: string;
  notice: string;
  result: ToolTestResult | null;
}

let nextKey = 0;
const cards = ref<Draft[]>([]);
const loading = ref(true);
const loadError = ref("");
const removing = ref<Draft | null>(null);
const search = ref("");
const filter = ref<"all" | "enabled" | "disabled">("all");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const selectedName = ref<string | null>(null);
const tab = ref("general");
const tabItems = [{ id: "general", label: "General" }, { id: "addresses", label: "Addresses" }];
const selected = computed(() => cards.value.find((draft) => draft.saved.name === selectedName.value) ?? null);
const options = computed(() => [
  { id: "all" as const, label: "All", count: cards.value.length },
  { id: "enabled" as const, label: "Enabled", count: cards.value.filter((d) => d.saved.enabled).length, tone: "success" as const },
  { id: "disabled" as const, label: "Disabled", count: cards.value.filter((d) => !d.saved.enabled).length, tone: "muted" as const },
]);
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return cards.value.filter((draft) => (filter.value === "all" || (filter.value === "enabled") === draft.saved.enabled)
    && `${draft.saved.label} ${draft.saved.name} ${draft.saved.origins.map((o) => o.origin ?? "").join(" ")}`.toLowerCase().includes(query));
});

const PORTS: Record<ToolService["name"], number> = { bard: 29400, scribe: 29401, reader: 29402 };
/** Where each tool service usually runs: on the shared Docker network, or on the computer that hosts Docker. */
function presetGroups(name: ToolService["name"]) {
  return [
    { title: "Shared Docker network", items: [{ label: `${name}:${PORTS[name]}`, address: `http://${name}:${PORTS[name]}` }] },
    { title: "This computer", items: [{ label: `host.docker.internal:${PORTS[name]}`, address: `http://host.docker.internal:${PORTS[name]}` }] },
  ];
}
const preset = ref("");

function usePreset(draft: Draft) {
  const row = draft.addresses[0];
  const address = preset.value;
  preset.value = "";
  if (!row || !address) return;
  row.address = address;
  addressChanged(row);
  void check(draft, row);
}

function addressRow(): AddressRow {
  return { key: nextKey++, address: "", name: "", found: null, hasOverride: false,
    token: "", lookup: 0, checking: false, error: "" };
}

function apply(draft: Draft, saved: ToolService) {
  draft.saved = saved;
  draft.enabled = saved.enabled;
  draft.token = "";
  draft.addresses = saved.origins.length
    ? saved.origins.map((origin) => ({
        ...addressRow(), address: origin.origin ?? "", found: origin.origin ? true : null,
        hasOverride: origin.has_override, error: origin.origin ? "" : "This address left Treasury’s catalog.",
      }))
    : [addressRow()];
  draft.result = null;
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    cards.value = (await toolServicesClient.list()).map((saved) => {
      const draft: Draft = { saved, enabled: saved.enabled, token: "", addresses: [],
        pending: null, error: "", notice: "", result: null };
      apply(draft, saved);
      return draft;
    });
  } catch (error) {
    loadError.value = errorMessage(error);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function addressChanged(row: AddressRow) {
  row.lookup++;
  row.checking = false;
  row.found = null;
  row.name = row.token = row.error = "";
  row.hasOverride = false;
}

async function check(draft: Draft, row: AddressRow) {
  const address = row.address.trim();
  if (!address || row.checking || (row.found === true && row.name)) return;
  const lookup = ++row.lookup;
  const current = () => draft.addresses.includes(row) && row.lookup === lookup;
  row.checking = true;
  row.error = "";
  try {
    const result = await toolServicesClient.lookup(address);
    if (!current()) return;
    row.found = result.found;
    if (result.found && result.group) row.name = result.group.name;
  } catch (error) {
    if (current()) row.error = errorMessage(error);
  } finally {
    if (current()) row.checking = false;
  }
}

function hasAddresses(draft: Draft): boolean {
  return draft.saved.origins.length > 0 || draft.addresses.length > 1 || draft.addresses.some((row) => !!row.address.trim());
}

function canSave(draft: Draft): boolean {
  if (!hasAddresses(draft)) return draft.enabled !== draft.saved.enabled || !!draft.token;
  return draft.addresses.every((row) => !!row.address.trim() && !row.checking && !row.error
    && (row.found === true || (row.found === false && !!row.name.trim())));
}

async function save(draft: Draft) {
  if (draft.pending || !canSave(draft)) return;
  const body: ToolSaveBody = { enabled: draft.enabled };
  if (draft.token) body.token = draft.token;
  if (hasAddresses(draft)) {
    body.addresses = draft.addresses.map((row) => ({
      address: row.address.trim(),
      ...(row.found ? {} : { name: row.name.trim() }),
      ...(row.token ? { header_value: row.token } : {}),
    }));
  }
  await run(draft, "save", async () => {
    apply(draft, await toolServicesClient.save(draft.saved.name, body));
    draft.notice = "Connection saved.";
  });
}

async function run(draft: Draft, action: NonNullable<Draft["pending"]>, perform: () => Promise<void>) {
  if (draft.pending) return;
  draft.pending = action;
  draft.error = draft.notice = "";
  draft.result = null;
  try {
    await perform();
  } catch (error) {
    draft.error = errorMessage(error);
  } finally {
    draft.pending = null;
  }
}

async function test(draft: Draft) {
  await run(draft, "test", async () => { draft.result = await toolServicesClient.test(draft.saved.name); });
}

async function clear() {
  const draft = removing.value;
  if (!draft || draft.pending) return;
  await run(draft, "clear", async () => {
    apply(draft, await toolServicesClient.clear(draft.saved.name));
    draft.notice = "Connection removed.";
  });
  removing.value = null;
}

/** Whether the draft differs from what Stronghold saved: the drawer then asks before it closes. */
function isDirty(draft: Draft): boolean {
  if (draft.enabled !== draft.saved.enabled || draft.token) return true;
  if (draft.addresses.length !== Math.max(1, draft.saved.origins.length)) return true;
  return draft.addresses.some((row, index) => row.address.trim() !== (draft.saved.origins[index]?.origin ?? "")
    || !!row.token || (row.found === false && !!row.name.trim()));
}

function discard(draft: Draft) {
  apply(draft, draft.saved);
  draft.error = draft.notice = "";
}

function closeDrawer() {
  if (selected.value) discard(selected.value);
  selectedName.value = null;
}

/** What a status means and what to do about it; the table and the drawer show it in a helper popover. */
function statusHelp(saved: { ready: boolean; reason?: string | null; name: string }): string {
  if (saved.ready) return "Stronghold can reach this service. Nothing to do. Use Test to check the connection again.";
  return `${saved.reason ?? "This service is not ready."} Open the service, turn it on, set its address and token, then save and run Test.`;
}

function enabledHelp(enabled: boolean): string {
  return enabled
    ? "Citadel services may call this service. Open it and turn Enabled off to stop calls without losing its addresses."
    : "Citadel services do not call this service. Open it and turn Enabled on to start using it.";
}

function resultAddress(draft: Draft, originId: string): string {
  return draft.saved.origins.find((origin) => origin.origin_id === originId)?.origin ?? "Unavailable address";
}
watch(selectedName, () => { tab.value = "general"; });
</script>

<template>
  <PageLayout class="admin-panel" title="Tool services" wide>
    <StatusFilters v-if="!loading && !loadError" v-model="filter" label="Filter tool services" :options="options" />
    <section class="admin-panel-card" aria-labelledby="tool-services-title">
      <header class="admin-panel-head">
        <h2 id="tool-services-title">Tool services</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Tool services">
            <p>Citadel services call Bard, Scribe and Reader through these addresses. Treasury stores the addresses. Stronghold keeps the tokens and never displays them again.</p>
            <p>Open a service to change its addresses and tokens. Add a backup address to keep working when the first one is down.</p>
          </PanelHelp>
          <AdminSearch ref="searchField" v-model="search" label="Search tool services" />
        </div>
      </header>
      <p v-if="loading" class="admin-panel-text muted" role="status">Loading…</p>
      <ActionMessage v-else-if="loadError" kind="error" :text="loadError" class="admin-panel-text"><button class="chip" type="button" @click="load">Retry</button></ActionMessage>
      <p v-else-if="!visible.length" class="admin-panel-text muted">No tool services match. <button v-if="search || filter !== 'all'" type="button" class="chip" @click="search = ''; filter = 'all'; searchField?.focus()">Clear filters</button></p>
      <div v-else class="admin-table-scroll" role="region" aria-labelledby="tool-services-title" tabindex="0">
        <table class="admin-records">
          <thead><tr><th scope="col">Service</th><th scope="col">Status</th><th scope="col">Enabled</th><th scope="col">Addresses</th><th scope="col">Test</th><th scope="col">Result</th></tr></thead>
          <tbody>
            <tr v-for="draft in visible" :key="draft.saved.name" :data-test="'row-' + draft.saved.name">
              <th scope="row">
                <div class="admin-record-name"><span class="admin-record-badge" aria-hidden="true">{{ draft.saved.label.slice(0, 2).toUpperCase() }}</span><div>
                  <button type="button" class="admin-row-button" aria-haspopup="dialog" :aria-label="`Open ${draft.saved.label}`" @click="selectedName = draft.saved.name">{{ draft.saved.label }}</button>
                  <code>{{ draft.saved.name }}</code>
                </div></div>
              </th>
              <td>
                <div class="status-cell"><span class="pill" :class="{ ready: draft.saved.ready }"><span aria-hidden="true">{{ draft.saved.ready ? "✓" : "○" }}</span> {{ draft.saved.ready ? "Ready" : "Not ready" }}</span>
                <PanelHelp v-if="!draft.saved.ready" title="Not ready"><p>{{ statusHelp(draft.saved) }}</p></PanelHelp></div>
              </td>
              <td><div class="status-cell"><span class="pill" :class="{ on: draft.saved.enabled }">{{ draft.saved.enabled ? "On" : "Off" }}</span>
                <PanelHelp v-if="!draft.saved.enabled" title="Off"><p>{{ enabledHelp(draft.saved.enabled) }}</p></PanelHelp></div></td>
              <td class="count">{{ draft.saved.origins.length }}</td>
              <TestResultCells :id="draft.saved.name" :label="draft.saved.label" :testing="draft.pending === 'test'" :busy="!!draft.pending"
                :result="draft.result" @test="test(draft)" />
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <RecordDrawer ref="drawer" :open="selected !== null" :title="selected?.saved.label ?? 'Tool service'" :editing="!!selected && isDirty(selected)" :busy="!!selected?.pending"
      :fallback-focus="() => searchField?.focus()" @discard="selected && discard(selected)" @save="selected && save(selected)" @close="closeDrawer">
      <form v-if="selected" class="service" :aria-label="selected.saved.label" :data-test="'service-' + selected.saved.name" @submit.prevent="drawer?.requestSave()">
        <FormTabs v-model="tab" :items="tabItems" prefix="tool" label="Service settings" />
        <section v-show="tab === 'general'" id="tool-panel-general" class="pane" role="tabpanel" aria-labelledby="tool-tab-general">
        <div class="summary">
          <span class="admin-record-badge big" aria-hidden="true">{{ selected.saved.label.slice(0, 2).toUpperCase() }}</span>
          <div class="summary-copy"><span class="eyebrow">Tool service</span><code>{{ selected.saved.name }}</code></div>
          <span class="pill" :class="{ ready: selected.saved.ready }"><span aria-hidden="true">{{ selected.saved.ready ? "✓" : "○" }}</span> {{ selected.saved.ready ? "Ready" : "Not ready" }}</span>
          <PanelHelp v-if="!selected.saved.ready" title="Not ready"><p>{{ statusHelp(selected.saved) }}</p></PanelHelp>
        </div>

        <section class="group">
        <h4>Connection</h4>
        <ToggleSwitch
          :checked="selected.enabled"
          :disabled="!!selected.pending"
          @change="selected.enabled = ($event.target as HTMLInputElement).checked"
        >Enabled</ToggleSwitch>

        <PasswordInput
          v-model="selected.token"
          label="Connection token"
          autocomplete="new-password"
          :placeholder="selected.saved.has_token ? 'Leave empty to keep the saved token' : undefined"
          :disabled="!!selected.pending"
        />
        <p class="help">The token is saved in Stronghold and never shown again.</p>
        </section>

        </section>
        <section v-show="tab === 'addresses'" id="tool-panel-addresses" class="pane" role="tabpanel" aria-labelledby="tool-tab-addresses">
        <section class="group">
        <h4>Addresses</h4>
        <p class="help">Tried in order. The first is primary; the rest are used when the one before it is down.</p>
        <div class="field">
          <label for="tool-preset">Preset</label>
          <select id="tool-preset" v-model="preset" data-test="preset" :disabled="!!selected.pending" @change="usePreset(selected)">
            <option value="">None</option>
            <optgroup v-for="group in presetGroups(selected.saved.name)" :key="group.title" :label="group.title">
              <option v-for="item in group.items" :key="item.address" :value="item.address">{{ item.label }}</option>
            </optgroup>
          </select>
          <p class="help">Fills the primary address. Edit it if yours differs.</p>
        </div>

        <fieldset v-for="(row, index) in selected.addresses" :key="row.key" class="address-row" :disabled="!!selected.pending">
          <legend>{{ index === 0 ? "Primary address" : "Backup address " + index }}</legend>
          <div class="field">
            <label :for="'address-' + row.key">Address</label>
            <input
              :id="'address-' + row.key"
              v-model="row.address"
              type="url"
              autocomplete="off"
              spellcheck="false"
              :data-test="'address-' + index"
              :aria-invalid="!!row.error"
              :aria-describedby="row.error ? 'address-error-' + row.key : undefined"
              @input="addressChanged(row)"
              @blur="check(selected, row)"
            />
            <p v-if="row.checking" class="help" role="status">Checking Treasury…</p>
            <ActionMessage v-if="row.error" kind="error" :text="row.error" :id="'address-error-' + row.key" />
          </div>
          <div v-if="row.found === false || row.name" class="field">
            <label :for="'service-name-' + row.key">Outside service name</label>
            <input
              :id="'service-name-' + row.key"
              v-model="row.name"
              :readonly="row.found === true"
              :required="row.found === false"
              autocomplete="off"
              spellcheck="false"
              :data-test="'name-' + index"
            />
          </div>
          <PasswordInput
            v-model="row.token"
            label="Address token (optional)"
            autocomplete="new-password"
            :placeholder="row.hasOverride ? 'Leave empty to keep the saved token' : undefined"
            :disabled="!!selected.pending"
          />
          <div v-if="selected.addresses.length > 1">
            <button class="admin-icon" type="button" title="Remove address" aria-label="Remove address" @click="selected.addresses.splice(index, 1)">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13" /></svg>
            </button>
          </div>
        </fieldset>

        <div>
          <button class="admin-icon" type="button" title="Add a backup address" aria-label="Add a backup address" data-test="add-address" :disabled="!!selected.pending" @click="selected.addresses.push(addressRow())">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>
        </section>
        </section>
        <ActionMessage v-if="selected.error" kind="error" :text="selected.error" />
        <p v-if="selected.notice" class="help" role="status">{{ selected.notice }}</p>
        <div v-if="selected.result" class="result" :class="selected.result.ok ? 'ok' : 'bad'" data-test="test-result" role="status">
          <strong>{{ selected.result.ok ? "Connected" : "Test failed" }}</strong>
          <p>{{ selected.result.message }}</p>
          <ul v-if="selected.result.origins.length">
            <li v-for="origin in selected.result.origins" :key="origin.origin_id">
              {{ resultAddress(selected, origin.origin_id) }} — {{ origin.message }}
            </li>
          </ul>
        </div>
        <section v-if="selected.saved.origins.length || selected.saved.has_token || !selected.saved.enabled" class="danger-zone">
          <h4>Danger zone</h4>
          <p class="help">Clears the saved addresses and tokens from Stronghold. The addresses stay in Treasury.</p>
          <button class="danger" type="button" data-test="clear" :disabled="!!selected.pending" @click="removing = selected">Remove connection</button>
        </section>
      </form>
      <template v-if="selected" #footer>
        <button class="chip" type="button" data-test="test" :disabled="!!selected.pending" :aria-busy="selected.pending === 'test'" @click="test(selected)">{{ selected.pending === "test" ? "Testing…" : "Test" }}</button>
        <button class="chip" type="button" data-test="cancel" :disabled="!!selected.pending || !isDirty(selected)" @click="drawer?.requestCancel()">Cancel</button>
        <button class="primary" type="button" data-test="save" :disabled="!!selected.pending || !isDirty(selected) || !canSave(selected)" :aria-busy="selected.pending === 'save'" @click="drawer?.requestSave()">{{ selected.pending === "save" ? "Saving…" : "Save" }}</button>
      </template>
    </RecordDrawer>

    <ConfirmModal
      :open="removing !== null"
      :title="'Remove ' + (removing?.saved.label ?? '') + ' connection?'"
      message="This clears the saved addresses and tokens from Stronghold. The addresses stay in Treasury."
      confirm-label="Remove connection"
      danger
      :busy="removing?.pending === 'clear'"
      @close="removing = null"
      @confirm="clear"
    />
  </PageLayout>
</template>

<style scoped>
.pane { display: grid; gap: 16px; min-width: 0; }
.pill { display: inline-flex; align-items: center; gap: 5px; padding: 2px 10px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; color: var(--muted); white-space: nowrap; }
.pill.ready { color: var(--success); background: color-mix(in srgb, var(--success) 8%, var(--bg)); }
.pill.on { color: var(--text); }
.status-cell { display: flex; align-items: center; gap: 4px; }
.count { font-variant-numeric: tabular-nums; }
.summary { display: flex; align-items: center; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.summary-copy { flex: 1; min-width: 0; }
.summary-copy { display: grid; gap: 2px; }
.eyebrow { font-size: 0.75em; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
.summary code { font-size: 0.95em; color: var(--text); }
.admin-record-badge.big { width: 44px; height: 44px; color: var(--accent); }
.group { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.group h4 { margin: 0; font-size: 0.9em; }
.result { display: grid; gap: 4px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.result.ok { border-color: color-mix(in srgb, var(--success) 50%, var(--border)); }
.result.bad { border-color: var(--danger); }
.result strong { font-size: 0.85em; }
.result ul { margin: 4px 0 0; padding-left: 18px; font-size: 0.9em; }
.danger-zone { display: grid; gap: 8px; justify-items: start; padding: 14px; border: 1px solid color-mix(in srgb, var(--danger) 45%, var(--border)); border-radius: var(--radius-lg); }
.danger-zone h4 { margin: 0; font-size: 0.9em; color: var(--danger); }
.service { display: grid; gap: 12px; min-width: 0; padding-top: 4px; }
.service p { margin: 0; overflow-wrap: anywhere; }
.state, .help { color: var(--muted); font-size: 0.9em; }
.state.ready { color: var(--success); }
.address-row { display: grid; gap: 10px; min-width: 0; margin: 0; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.address-row legend { padding: 0 4px; font-size: 0.9em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field label { font-size: 0.9em; font-weight: 600; }
.field select { min-height: 44px; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.field input { min-width: 0; min-height: 44px; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.error { color: var(--danger); }
.muted { color: var(--muted); }
.remove { padding-top: 12px; border-top: 1px solid var(--border); }
.service li { overflow-wrap: anywhere; }
</style>
