<script setup lang="ts">
import FieldLabel from "../components/admin/FieldLabel.vue";
import ActionMessage from "../components/admin/ActionMessage.vue";
import { computed, onMounted, ref, watch } from "vue";
import { treasuryAdminClient, type CacheDefaults, type ConnectionRow, type ConnectionSpec, type ConnectionsView } from "../api/TreasuryAdminClient";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import DraftActions from "../components/admin/DraftActions.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import FormTabs from "../components/admin/FormTabs.vue";
import StatusFilters from "../components/admin/StatusFilters.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { useDraftPanel } from "../composables/useDraftPanel";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** The databases Treasury keeps data in. Four local SQLite files are built in so the stack works on a new install;
 * what is saved here replaces or adds to them. A new connection is offered to the instances at once, a changed or
 * removed one is used from Treasury's next start. A Postgres address is a ${NAME} placeholder: its value stays in
 * Treasury's .env, so no secret is saved here. */
const view = ref<ConnectionsView | null>(null);
const loading = ref(true);
const error = ref("");
const notice = ref("");
const busy = ref(false);

const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
type Filter = "all" | ConnectionRow["source"];
const filter = ref<Filter>("all");
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const formEl = ref<HTMLFormElement>();
const selectedName = ref<string | null>(null);
const creating = ref(false);
const editing = ref(false);
const tab = ref("general");
const tabItems = [{ id: "general", label: "General" }, { id: "options", label: "Options" }];
const formError = ref("");

const name = ref("");
const type = ref<ConnectionSpec["type"]>("sqlite");
const path = ref("");
const dsn = ref("");
const poolSize = ref("");
const project = ref("");
const credentials = ref("");
const database = ref("");
const rawSql = ref(false);
const cacheTtl = ref("");
const removing = ref<ConnectionRow | null>(null);

const cacheTtlDefault = ref("");
const cacheEntries = ref("");
const cacheNegative = ref("");
const cacheSearch = ref("");
const cacheSearchField = ref<InstanceType<typeof AdminSearch>>();

const rows = computed(() => view.value?.connections ?? []);
const selected = computed(() => rows.value.find((r) => r.name === selectedName.value) ?? null);
const drawerOpen = computed(() => selected.value !== null || creating.value);
const sources = { "built-in": "Built-in", saved: "Saved", changed: "Changed" } as const;
const options = computed(() => [
  { id: "all", label: "All", count: rows.value.length, tone: "accent" },
  ...(["built-in", "saved", "changed"] as const).map((id) => ({ id, label: sources[id], count: rows.value.filter((r) => r.source === id).length, tone: (id === "changed" ? "warning" : "muted") as "warning" | "muted", disabled: !rows.value.some((r) => r.source === id) })),
] as const);
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return rows.value.filter((r) => (filter.value === "all" || r.source === filter.value)
    && [r.name, r.spec.type, where(r), ...r.used_by].some((text) => text.toLowerCase().includes(query)));
});

function applyView(next: ConnectionsView) {
  view.value = next;
  resetCache();
}

function resetCache() {
  const saved = view.value?.default_cache;
  if (!saved) return;
  cacheTtlDefault.value = String(saved.ttl_seconds);
  cacheEntries.value = String(saved.max_entries);
  cacheNegative.value = String(saved.negative_ttl_seconds);
}

async function load() {
  try {
    applyView(await treasuryAdminClient.connections());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function fill(row: ConnectionRow | null) {
  const spec = row?.spec;
  name.value = row?.name ?? "";
  type.value = spec?.type ?? "sqlite";
  path.value = spec?.path ?? "";
  dsn.value = spec?.dsn ?? "";
  poolSize.value = spec?.max_pool_size ? String(spec.max_pool_size) : "";
  project.value = spec?.project ?? "";
  credentials.value = spec?.credentials_file ?? "";
  database.value = spec?.database ?? "";
  rawSql.value = spec?.allow_raw_sql ?? false;
  cacheTtl.value = spec?.cache?.ttl_seconds !== undefined ? String(spec.cache.ttl_seconds) : "";
  formError.value = "";
}

function openRow(row: ConnectionRow) {
  fill(row);
  creating.value = false;
  editing.value = false;
  selectedName.value = row.name;
  error.value = notice.value = "";
}

function openCreate() {
  fill(null);
  selectedName.value = null;
  creating.value = true;
  editing.value = true;
  error.value = notice.value = "";
}

function close() {
  selectedName.value = null;
  creating.value = false;
  editing.value = false;
}

function discard() {
  if (creating.value) close();
  else { fill(selected.value); editing.value = false; }
}

function spec(): ConnectionSpec {
  const out: ConnectionSpec = { type: type.value };
  if (type.value === "sqlite") out.path = path.value.trim();
  if (type.value === "postgres") {
    out.dsn = dsn.value.trim();
    if (String(poolSize.value).trim()) out.max_pool_size = Number(poolSize.value);
  }
  if (type.value === "firestore") {
    if (project.value.trim()) out.project = project.value.trim();
    if (credentials.value.trim()) out.credentials_file = credentials.value.trim();
    if (database.value.trim()) out.database = database.value.trim();
  }
  if (rawSql.value) out.allow_raw_sql = true;
  if (String(cacheTtl.value).trim() !== "") out.cache = { ttl_seconds: Number(cacheTtl.value) };
  return out;
}

/** Validates before the drawer asks for confirmation. */
function requestSave() {
  if (formEl.value && !formEl.value.reportValidity()) return;
  drawer.value?.requestSave();
}

async function save() {
  busy.value = true;
  formError.value = notice.value = "";
  try {
    const next = await treasuryAdminClient.saveConnection(name.value.trim(), spec());
    applyView(next);
    notice.value = next.applies === "now" ? "Saved. Treasury offers it to the instances now." : "Saved. Treasury uses the change from its next start.";
    close();
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function remove() {
  if (!removing.value) return;
  busy.value = true;
  error.value = notice.value = "";
  try {
    applyView(await treasuryAdminClient.removeConnection(removing.value.name));
    notice.value = "Removed. Treasury uses the change from its next start.";
    close();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
    removing.value = null;
  }
}

async function saveCache(changes: Partial<CacheDefaults> | null) {
  busy.value = true;
  error.value = notice.value = "";
  try {
    applyView(await treasuryAdminClient.saveDefaultCache(changes));
    notice.value = "Saved. Treasury uses the cache defaults from its next start.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

const cacheChanged = computed(() => {
  const saved = view.value?.default_cache;
  if (!saved) return false;
  return String(cacheTtlDefault.value) !== String(saved.ttl_seconds) || String(cacheEntries.value) !== String(saved.max_entries) || String(cacheNegative.value) !== String(saved.negative_ttl_seconds);
});
const { discardOpen, keepFocus, answerDiscard } = useDraftPanel(cacheChanged, cacheSearchField);
const cacheFields = [
  { id: "default-ttl", label: "Keep an entry for (seconds)", help: "How long a looked-up record is kept before it is read from the database again. 0 turns the cache off.", words: "keep entry seconds ttl" },
  { id: "default-entries", label: "Most entries", help: "The most records kept at once. When it is full, the entry used least recently is dropped. 0 turns the cache off.", words: "most entries maximum" },
  { id: "default-negative", label: "Remember a missing record for (seconds)", help: "How long \"not found\" is remembered for a record that does not exist, so the database is not asked again at once.", words: "remember missing record negative seconds" },
] as const;
const showField = (words: string) => words.includes(cacheSearch.value.trim().toLowerCase());

function submitCache() {
  void keepFocus(() => saveCache({ ttl_seconds: Number(cacheTtlDefault.value), max_entries: Number(cacheEntries.value), negative_ttl_seconds: Number(cacheNegative.value) }));
}

function where(row: ConnectionRow): string {
  const s = row.spec;
  if (s.type === "sqlite") return s.path ?? "";
  if (s.type === "postgres") return s.dsn ?? "";
  return [s.project, s.database].filter(Boolean).join(" / ") || "default project";
}
watch([editing, creating], () => { tab.value = "general"; });
</script>

<template>
  <PageLayout class="admin-panel" title="Connections" wide>
    <StatusFilters v-model="filter" label="Filter connections" :options="options" />
    <ActionMessage v-if="error" kind="error" :text="error" />
    <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>

    <section class="admin-panel-card" aria-labelledby="connection-roster">
      <header class="admin-panel-head">
        <h2 id="connection-roster">Connections</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Connections">
            <p>The databases Treasury keeps data in. Four local ones are built in. What you save here replaces or adds to them.</p>
            <p>A new connection is offered to the instances at once. A changed or removed one is used from Treasury's next start.</p>
            <p>A Postgres address is a <code>${NAME}</code> placeholder: put the real address in Treasury's .env under that name. No secret is saved here.</p>
          </PanelHelp>
          <button type="button" class="admin-icon accent" data-test="add" aria-label="Add connection" title="Add connection" :disabled="loading || !view" @click="openCreate"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button>
          <AdminSearch ref="searchField" v-model="search" label="Search connections" />
        </div>
      </header>
      <p v-if="loading" class="admin-panel-text muted" role="status">Loading…</p>
      <p v-else-if="view && !visible.length" class="admin-panel-text muted">No connections match. <button v-if="search || filter !== 'all'" type="button" class="chip" @click="search = ''; filter = 'all'; searchField?.focus()">Clear filters</button></p>
      <div v-else-if="view" class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="connection-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">Name</th><th scope="col">Type</th><th scope="col">Where</th><th scope="col">Used by</th></tr></thead>
          <tbody>
            <tr v-for="row in visible" :key="row.name" :data-test="`row-${row.name}`">
              <th scope="row"><button type="button" class="admin-row-button" data-test="open" aria-haspopup="dialog" @click="openRow(row)">{{ row.name }}</button> <span class="tag">{{ row.source === "saved" ? "saved" : row.source }}</span></th>
              <td>{{ row.spec.type }}<span v-if="row.spec.allow_raw_sql" class="muted"> · raw SQL</span></td>
              <td>{{ where(row) }}</td>
              <td>{{ row.used_by.length ? row.used_by.join(", ") : "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="view" class="admin-panel-card cache" aria-labelledby="cache-title" data-test="cache-form">
      <header class="admin-panel-head">
        <h2 id="cache-title">Cache defaults <span v-if="view.default_cache_stored" class="tag">changed</span></h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Cache defaults"><p>What a connection uses when it sets no cache of its own. Used from Treasury's next start.</p></PanelHelp>
          <DraftActions :dirty="cacheChanged" :saving="busy" label="cache default changes" @cancel="discardOpen = true" @save="submitCache" />
          <AdminSearch ref="cacheSearchField" v-model="cacheSearch" label="Search cache defaults" />
        </div>
      </header>
      <div class="cache-body">
        <p class="lede">Used by every connection that sets none of its own.</p>
        <div v-for="field in cacheFields" v-show="showField(field.words)" :key="field.id" class="field">
          <FieldLabel :title="field.label" :for="field.id">{{ field.help }}</FieldLabel>
          <input v-if="field.id === 'default-ttl'" :id="field.id" v-model="cacheTtlDefault" type="number" min="0" :disabled="busy" :data-test="field.id" />
          <input v-else-if="field.id === 'default-entries'" :id="field.id" v-model="cacheEntries" type="number" min="0" :disabled="busy" :data-test="field.id" />
          <input v-else :id="field.id" v-model="cacheNegative" type="number" min="0" :disabled="busy" :data-test="field.id" />
        </div>
        <button v-if="view.default_cache_stored" type="button" class="chip reset" :disabled="busy" data-test="cache-reset" @click="saveCache(null)">Use the built-in defaults</button>
      </div>
    </section>

    <RecordDrawer ref="drawer" :open="drawerOpen" :title="creating ? 'Add connection' : selected ? `Connection ${selected.name}` : 'Connection'" :editable="!creating" :editing="editing" :busy="busy"
      :save-label="creating ? 'Add connection' : 'Save connection'" :fallback-focus="() => searchField?.focus()" @edit="editing = true" @discard="discard" @save="save" @close="close">
      <form v-if="editing" ref="formEl" class="admin-editor" data-test="form" @submit.prevent="requestSave">
        <FormTabs v-model="tab" :items="tabItems" prefix="conn" label="Connection settings" />
        <section v-show="tab === 'general'" id="conn-panel-general" class="pane" role="tabpanel" aria-labelledby="conn-tab-general">
        <div class="field">
          <FieldLabel title="Name" for="c-name">Lowercase letters, digits and _. Saving a built-in name replaces that connection.</FieldLabel>
          <input id="c-name" v-model="name" required :disabled="!creating || busy" autocomplete="off" spellcheck="false" data-test="name" />
        </div>
        <div class="field">
          <FieldLabel title="Type" for="c-type">The kind of database: an SQLite file, Postgres or Firestore. The fields below change with it.</FieldLabel>
          <select id="c-type" v-model="type" :disabled="busy" data-test="type">
            <option value="sqlite">SQLite file</option>
            <option value="postgres">Postgres</option>
            <option value="firestore">Firestore</option>
          </select>
        </div>
        <div v-if="type === 'sqlite'" class="field">
          <FieldLabel title="File" for="c-path">Relative to Treasury's data folder.</FieldLabel>
          <input id="c-path" v-model="path" :disabled="busy" autocomplete="off" spellcheck="false" placeholder="reports.db" data-test="path" />
        </div>
        <template v-if="type === 'postgres'">
          <div class="field">
            <FieldLabel title="Address" for="c-dsn">A placeholder such as ${POSTGRES_DSN}. Put the real address in Treasury's .env under that name.</FieldLabel>
            <input id="c-dsn" v-model="dsn" :disabled="busy" autocomplete="off" spellcheck="false" placeholder="${POSTGRES_DSN}" data-test="dsn" />
          </div>
          <div class="field">
            <FieldLabel title="Pool size (optional)" for="c-pool">The most connections Treasury keeps open to this database. At least 1.</FieldLabel>
            <input id="c-pool" v-model="poolSize" type="number" min="1" :disabled="busy" data-test="pool" />
          </div>
        </template>
        <template v-if="type === 'firestore'">
          <div class="field"><label for="c-project">Project (optional)</label><input id="c-project" v-model="project" :disabled="busy" autocomplete="off" data-test="project" /></div>
          <div class="field"><label for="c-cred">Credentials file (optional)</label><input id="c-cred" v-model="credentials" :disabled="busy" autocomplete="off" data-test="credentials" /></div>
          <div class="field"><label for="c-db">Database (optional)</label><input id="c-db" v-model="database" :disabled="busy" autocomplete="off" data-test="database" /></div>
        </template>
        </section>
        <section v-show="tab === 'options'" id="conn-panel-options" class="pane" role="tabpanel" aria-labelledby="conn-tab-options">
        <ToggleSwitch :checked="rawSql" :disabled="busy" data-test="raw-sql" @change="rawSql = ($event.target as HTMLInputElement).checked">Allow raw SQL on this connection</ToggleSwitch>
        <div class="field">
          <FieldLabel title="Cache for this connection (seconds, optional)" for="c-cache">Empty uses the cache defaults. 0 turns the cache off for this connection.</FieldLabel>
          <input id="c-cache" v-model="cacheTtl" type="number" min="0" :disabled="busy" data-test="cache" />
        </div>
        </section>
      </form>
      <div v-else-if="selected" class="admin-details">
        <dl>
          <dt>Name</dt><dd>{{ selected.name }}</dd>
          <dt>Type</dt><dd>{{ selected.spec.type }}</dd>
          <dt>Where</dt><dd>{{ where(selected) }}</dd>
          <dt>Source</dt><dd>{{ sources[selected.source] }}</dd>
          <dt>Raw SQL</dt><dd>{{ selected.spec.allow_raw_sql ? "Allowed" : "Not allowed" }}</dd>
          <dt>Cache</dt><dd>{{ selected.spec.cache?.ttl_seconds !== undefined ? `${selected.spec.cache.ttl_seconds} seconds` : "Cache defaults" }}</dd>
          <dt>Used by</dt><dd>{{ selected.used_by.length ? selected.used_by.join(", ") : "—" }}</dd>
        </dl>
        <section v-if="selected.source !== 'built-in'" class="danger-zone">
          <h4>Danger zone</h4>
          <p class="muted">{{ selected.source === "changed" ? "Your saved version is dropped from Treasury's next start." : "Treasury stops offering it from its next start." }}</p>
          <button type="button" class="danger" data-test="remove" @click="removing = selected">{{ selected.source === "changed" ? "Use the built-in" : "Remove" }}</button>
        </section>
      </div>
      <ActionMessage v-if="formError" kind="error" :text="formError" />
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="busy" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="button" class="primary" :disabled="busy || !name.trim()" :aria-busy="busy" data-test="save" @click="requestSave">{{ creating ? "Add connection" : "Save changes" }}</button>
      </template>
    </RecordDrawer>

    <ConfirmModal
      :open="discardOpen"
      title="Discard unsaved changes?"
      message="Your cache default changes have not been saved."
      confirm-label="Discard changes"
      @confirm="answerDiscard(true, resetCache)"
      @close="answerDiscard(false, resetCache)"
    />
    <ConfirmModal
      :open="removing !== null"
      :title="removing?.source === 'changed' ? 'Use the built-in connection' : 'Remove connection'"
      :message="removing?.source === 'changed' ? `Put the built-in ${removing?.name} back? Your saved version is dropped from Treasury's next start.` : `Remove ${removing?.name ?? ''}? Treasury stops offering it from its next start.`"
      :confirm-label="removing?.source === 'changed' ? 'Use the built-in' : 'Remove'"
      danger
      :busy="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </PageLayout>
</template>

<style scoped>
.pane { display: grid; gap: 12px; min-width: 0; }
.error { margin: 0 0 12px; color: var(--danger); }
.cache { margin-top: 14px; }
.cache-body { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; align-items: start; padding: 14px; }
.cache-body > .lede, .cache-body > .reset { grid-column: 1 / -1; }
.lede { margin: 0; color: var(--muted); font-size: 0.9em; }
.tag { margin-left: 6px; padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.75em; font-weight: 400; color: var(--muted); }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .field > select { width: 100%; min-width: 0; min-height: 44px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.reset { justify-self: start; }
.danger-zone { display: grid; gap: 8px; margin-top: 16px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-md); justify-items: start; }
.danger-zone h4 { margin: 0; color: var(--danger); }
.danger-zone p { margin: 0; }
</style>
