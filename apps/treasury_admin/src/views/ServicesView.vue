<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { treasuryAdminClient, type ServiceRow, type ServicesView } from "../api/TreasuryAdminClient";
import { AdminSearch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { RecordDrawer } from "@citadel/ui";
import { StatusFilters } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { errorMessage } from "../utils/errors";
import "@citadel/ui/admin.css";

/** Where Citadel services reach each other. A pinned address takes precedence over registration. Editing happens
 * in the row's drawer; the displayed address changes only once Treasury has answered. */
const { getServices, putService, deleteService } = treasuryAdminClient;
const view = ref<ServicesView | null>(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const selectedName = ref<string | null>(null);
const editing = ref(false);
const draft = ref("");
type Filter = "all" | ServiceRow["source"];
const filter = ref<Filter>("all");
const labels = { pinned: "Pinned", registered: "Registered", default: "Default" } as const;
/** What each source means and how to change it, shown in the helper popover beside the source. */
const sourceHelp = {
  pinned: "You set this address by hand. It wins over the registered one. Open the service and remove the pin to go back to the registered address.",
  registered: "The service announced this address itself when it started. Open the service and pin an address to override it.",
  default: "No address is registered, so Treasury uses the built-in default. Start the service so it registers, or pin an address.",
} as const;

const rows = computed(() => view.value?.services ?? []);
const options = computed(() => [
  { id: "all", label: "All", count: rows.value.length, tone: "accent" },
  ...(["pinned", "registered", "default"] as const).map((id) => ({ id, label: labels[id], count: rows.value.filter((r) => r.source === id).length, tone: (id === "pinned" ? "warning" : "muted") as "warning" | "muted", disabled: !rows.value.some((r) => r.source === id) })),
] as const);
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return rows.value.filter((r) => (filter.value === "all" || r.source === filter.value) && [r.name, r.url, labels[r.source]].some((text) => text.toLowerCase().includes(query)));
});
const selected = computed(() => rows.value.find((r) => r.name === selectedName.value) ?? null);

onMounted(async () => {
  try { view.value = await getServices(); }
  catch (err) { error.value = errorMessage(err); }
  finally { loading.value = false; }
});

function select(row: ServiceRow) {
  selectedName.value = row.name;
  editing.value = false;
  error.value = "";
}

function close() {
  selectedName.value = null;
  editing.value = false;
}

function edit() {
  draft.value = selected.value?.pinned ?? selected.value?.url ?? "";
  error.value = "";
  editing.value = true;
}

/** Waits for Treasury to confirm before changing the displayed address. */
async function save(unpin = false) {
  const row = selected.value;
  if (!row || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    view.value = unpin ? await deleteService(row.name) : await putService(row.name, draft.value.trim());
    editing.value = false;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <PageLayout class="admin-panel" title="Services" wide>
    <StatusFilters v-model="filter" label="Filter services" :options="options" />
    <section class="admin-panel-card" aria-labelledby="service-roster">
      <header class="admin-panel-head">
        <h2 id="service-roster">Service addresses</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Service addresses"><p>Where Citadel services can reach each other. A pinned address takes precedence over registration.</p><p>Open a service to pin an address, or to go back to the address it registered.</p></PanelHelp>
          <AdminSearch ref="searchField" v-model="search" label="Search services" />
        </div>
      </header>
      <ActionMessage v-if="error && !selected" kind="error" :text="error" class="admin-panel-text" />
      <p v-if="loading" class="admin-panel-text muted" role="status">Loading…</p>
      <p v-else-if="view && !visible.length" class="admin-panel-text muted">No services match. <button v-if="search || filter !== 'all'" type="button" class="chip" @click="search = ''; filter = 'all'; searchField?.focus()">Clear filters</button></p>
      <div v-else-if="view" class="admin-table-scroll" role="region" aria-labelledby="service-roster" tabindex="0">
        <table class="admin-records">
          <thead><tr><th scope="col">Name</th><th scope="col">Address in use</th><th scope="col">Source</th></tr></thead>
          <tbody>
            <tr v-for="row in visible" :key="row.name" :data-test="'row-' + row.name">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="select(row)">{{ row.name }}</button></th>
              <td><code>{{ row.url }}</code></td>
              <td><div class="source-cell">{{ labels[row.source] }}<PanelHelp :title="labels[row.source]"><p>{{ sourceHelp[row.source] }}</p></PanelHelp></div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <RecordDrawer ref="drawer" :open="selected !== null" :title="selected ? `Service ${selected.name}` : 'Service details'" editable :editing="editing" :busy="busy" :note="editing && !draft.trim() ? 'Enter the address first.' : ''"
      save-label="Pin address" :fallback-focus="() => searchField?.focus()" @edit="edit" @discard="editing = false" @save="save()" @close="close">
      <div v-if="selected" class="admin-details">
        <dl>
          <dt>Address in use</dt><dd><code>{{ selected.url }}</code></dd>
          <dt>Source</dt><dd>{{ labels[selected.source] }}</dd>
          <dt>Registered</dt><dd>{{ selected.registered ?? "None" }}</dd>
          <dt>Pinned</dt><dd>{{ selected.pinned ?? "None" }}</dd>
        </dl>
        <form v-if="editing" id="service-pin" class="admin-editor" @submit.prevent="drawer?.requestSave()">
          <label :for="'pin-' + selected.name">Address for {{ selected.name }}</label>
          <input :id="'pin-' + selected.name" v-model="draft" :disabled="busy" autocomplete="off" spellcheck="false" :aria-describedby="error ? 'service-error' : undefined" />
        </form>
        <ActionMessage v-if="error" kind="error" :text="error" id="service-error" />
        <button v-if="selected.pinned && !editing" type="button" class="chip" data-test="unpin" :disabled="busy" :aria-busy="busy" @click="save(true)">Use the registered address</button>
      </div>
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="busy" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="button" class="primary" :disabled="busy || !draft.trim()" :aria-busy="busy" data-test="pin" @click="drawer?.requestSave()">Pin address</button>
      </template>
    </RecordDrawer>
  </PageLayout>
</template>

<style scoped>
.source-cell { display: flex; align-items: center; gap: 4px; }
.error { margin: 8px 0 0; }
</style>
