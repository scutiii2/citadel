<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { treasuryAdminClient, type OutsideGroup, type OutsideOrigin, type OutsideView } from "../api/TreasuryAdminClient";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

type Target = { group: OutsideGroup; origin?: OutsideOrigin };
type ViewError = { message: string; serviceId?: string; deleteId?: string };

const groups = ref<OutsideGroup[]>([]);
const drafts = ref<Record<string, string>>({});
const loading = ref(true);
const renaming = ref<string | null>(null);
const removing = ref(false);
const busy = computed(() => renaming.value !== null || removing.value);
const error = ref<ViewError | null>(null);
const target = ref<Target | null>(null);
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const selectedId = ref<string | null>(null);

function applyView(next: OutsideView, renamedId?: string) {
  const previousNames = new Map(groups.value.map((group) => [group.service_id, group.name]));
  drafts.value = Object.fromEntries(next.groups.map(({ service_id: id, name }) => {
    const draft = drafts.value[id];
    const keepDraft = id !== renamedId && draft !== undefined && draft !== previousNames.get(id);
    return [id, keepDraft ? draft : name];
  }));
  groups.value = next.groups;
}

onMounted(async () => {
  try {
    applyView(await treasuryAdminClient.getOutside());
  } catch (err) {
    error.value = { message: errorMessage(err) };
  } finally {
    loading.value = false;
  }
});

const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return groups.value.filter((g) => [g.name, g.service_id, ...g.origins.map((o) => o.origin)].some((text) => text.toLowerCase().includes(query)));
});
const selected = computed(() => groups.value.find((g) => g.service_id === selectedId.value) ?? null);

async function rename(group: OutsideGroup) {
  const id = group.service_id;
  const name = drafts.value[id]?.trim();
  if (busy.value || !name || name === group.name) return;
  renaming.value = id;
  error.value = null;
  try {
    const renamed = await treasuryAdminClient.renameOutside(id, name);
    applyView({ groups: groups.value.map((row) => row.service_id === id ? renamed : row) }, id);
    try {
      applyView(await treasuryAdminClient.getOutside());
    } catch (err) {
      error.value = { message: `Name saved. Could not refresh outside services. ${errorMessage(err)}` };
    }
  } catch (err) {
    error.value = { serviceId: id, message: errorMessage(err) };
  } finally {
    renaming.value = null;
  }
}

const message = computed(() => {
  const current = target.value;
  if (!current) return "";
  const question = current.origin
    ? `Remove ${current.origin.origin} from ${current.group.name}?`
    : `Remove ${current.group.name} and all its origins?`;
  return current.group.used_by.length
    ? `${question} In use by ${current.group.used_by.join(", ")}. Removing this entry can disrupt their connections.`
    : question;
});

function closeConfirmation() {
  if (!removing.value) target.value = null;
}

async function remove() {
  const current = target.value;
  if (!current || busy.value) return;
  removing.value = true;
  error.value = null;
  try {
    const next = current.origin
      ? await treasuryAdminClient.deleteOutsideOrigin(current.origin.origin_id)
      : await treasuryAdminClient.deleteOutsideGroup(current.group.service_id);
    applyView(next);
    if (!current.origin) selectedId.value = null;
  } catch (err) {
    error.value = { message: errorMessage(err), deleteId: current.origin?.origin_id ?? current.group.service_id };
  } finally {
    removing.value = false;
    closeConfirmation();
  }
}
</script>

<template>
  <PageLayout class="admin-panel" title="Outside services" wide>
    <section class="admin-panel-card" aria-labelledby="outside-roster">
      <header class="admin-panel-head">
        <h2 id="outside-roster">Outside services</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Outside services"><p>Services outside Citadel and the addresses they are reached at. A service keeps its id when you rename it; the name is only a label.</p><p>Open a service to rename it or remove it or one of its origins.</p></PanelHelp>
          <AdminSearch ref="searchField" v-model="search" label="Search outside services" />
        </div>
      </header>
      <p v-if="error && !error.serviceId && !error.deleteId" class="admin-panel-text error" role="alert">{{ error.message }}</p>
      <p v-if="loading" class="admin-panel-text muted" role="status">Loading…</p>
      <p v-else-if="!error && !groups.length" class="admin-panel-text muted">No outside services yet.</p>
      <p v-else-if="groups.length && !visible.length" class="admin-panel-text muted">No outside services match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <div v-else-if="groups.length" class="admin-table-scroll" role="region" aria-labelledby="outside-roster" tabindex="0">
        <table class="admin-records">
          <thead><tr><th scope="col">Name</th><th scope="col">Origins</th><th scope="col">Used by</th></tr></thead>
          <tbody>
            <tr v-for="group in visible" :key="group.service_id" :data-test="'group-' + group.name">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="selectedId = group.service_id">{{ group.name }}</button></th>
              <td>
                <ul v-if="group.origins.length" class="origins"><li v-for="origin in group.origins" :key="origin.origin_id"><code>{{ origin.origin }}</code></li></ul>
                <span v-else class="muted">No origins</span>
              </td>
              <td>{{ group.used_by.length ? group.used_by.join(", ") : "Not used" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <RecordDrawer :open="selected !== null" :title="selected ? `Outside service ${selected.name}` : 'Outside service'" :fallback-focus="() => searchField?.focus()" @close="selectedId = null">
      <div v-if="selected" class="admin-details">
        <form class="admin-editor rename" @submit.prevent="rename(selected)">
          <label :for="'name-' + selected.service_id">Name of {{ selected.name }}</label>
          <input
            :id="'name-' + selected.service_id"
            v-model="drafts[selected.service_id]"
            :disabled="busy"
            :aria-invalid="error?.serviceId === selected.service_id || undefined"
            :aria-describedby="error?.serviceId === selected.service_id ? 'error-' + selected.service_id : undefined"
            autocomplete="off"
            spellcheck="false"
          />
          <p v-if="error?.serviceId === selected.service_id" :id="'error-' + selected.service_id" class="error" role="alert">{{ error.message }}</p>
          <button type="submit" class="primary" :disabled="busy || !drafts[selected.service_id]?.trim() || drafts[selected.service_id]?.trim() === selected.name" :aria-busy="renaming === selected.service_id">Rename</button>
        </form>
        <p v-if="error && !error.serviceId && !error.deleteId" class="error" role="alert">{{ error.message }}</p>
        <h4>Origins</h4>
        <ul v-if="selected.origins.length" class="origin-list">
          <li v-for="origin in selected.origins" :key="origin.origin_id">
            <code>{{ origin.origin }}</code>
            <button type="button" class="danger" :data-test="'delete-origin-' + origin.origin_id" :aria-label="'Remove origin ' + origin.origin" :aria-describedby="error?.deleteId === origin.origin_id ? 'delete-origin-error-' + origin.origin_id : undefined" :disabled="busy" @click="target = { group: selected, origin }">Remove origin</button>
            <p v-if="error?.deleteId === origin.origin_id" :id="'delete-origin-error-' + origin.origin_id" class="error delete-error" role="alert">{{ error.message }}</p>
          </li>
        </ul>
        <p v-else class="muted">No origins</p>
        <dl><dt>Used by</dt><dd>{{ selected.used_by.length ? selected.used_by.join(", ") : "Not used" }}</dd></dl>
        <section class="danger-zone">
          <h4>Danger zone</h4>
          <p class="muted">Removes this service and all its origins. Services that use it can lose their connection.</p>
          <button type="button" class="danger" data-test="delete-group" :aria-label="'Remove service ' + selected.name" :aria-describedby="error?.deleteId === selected.service_id ? 'delete-service-error-' + selected.service_id : undefined" :disabled="busy" @click="target = { group: selected }">Remove service</button>
          <p v-if="error?.deleteId === selected.service_id" :id="'delete-service-error-' + selected.service_id" class="error delete-error" role="alert">{{ error.message }}</p>
        </section>
      </div>
    </RecordDrawer>

    <ConfirmModal
      :open="target !== null"
      :title="target?.origin ? 'Remove origin' : 'Remove outside service'"
      :message="message"
      confirm-label="Remove"
      danger
      :busy="removing"
      @confirm="remove"
      @close="closeConfirmation"
    />
  </PageLayout>
</template>

<style scoped>
.origins { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; }
.origins code { min-width: 0; overflow-wrap: anywhere; }
h4 { margin: 14px 0 6px; font-size: 0.9em; }
.origin-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.origin-list li { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.origin-list code { min-width: 0; overflow-wrap: anywhere; }
.delete-error { flex-basis: 100%; margin: 4px 0 0; overflow-wrap: anywhere; }
.error { margin: 0; }
.danger-zone { display: grid; gap: 8px; margin-top: 16px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-md); justify-items: start; }
.danger-zone h4 { margin: 0; color: var(--danger); }
.danger-zone p { margin: 0; }
</style>
