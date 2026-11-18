<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { treasuryAdminClient, type CacheDefaults, type ConnectionRow, type ConnectionSpec, type ConnectionsView } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** The databases Treasury keeps data in. Four local SQLite files are built in so the stack works on a new install;
 * what is saved here replaces or adds to them. A new connection is offered to the instances at once, a changed or
 * removed one is used from Treasury's next start. A Postgres address is a ${NAME} placeholder: its value stays in
 * Treasury's .env, so no secret is saved here. */
const view = ref<ConnectionsView | null>(null);
const loading = ref(true);
const error = ref("");
const notice = ref("");
const busy = ref(false);

const editing = ref<string | null>(null); // the name being edited; "" while adding
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

const isNew = computed(() => editing.value === "");
const formError = ref("");

function applyView(next: ConnectionsView) {
  view.value = next;
  cacheTtlDefault.value = String(next.default_cache.ttl_seconds);
  cacheEntries.value = String(next.default_cache.max_entries);
  cacheNegative.value = String(next.default_cache.negative_ttl_seconds);
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

function open(row: ConnectionRow | null) {
  editing.value = row ? row.name : "";
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
  formError.value = error.value = notice.value = "";
}

function close() {
  editing.value = null;
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

function submitCache() {
  void saveCache({ ttl_seconds: Number(cacheTtlDefault.value), max_entries: Number(cacheEntries.value), negative_ttl_seconds: Number(cacheNegative.value) });
}

function where(row: ConnectionRow): string {
  const s = row.spec;
  if (s.type === "sqlite") return s.path ?? "";
  if (s.type === "postgres") return s.dsn ?? "";
  return [s.project, s.database].filter(Boolean).join(" / ") || "default project";
}
</script>

<template>
  <PageLayout
    class="info-content connections"
    title="Connections"
    description="The databases Treasury keeps data in. Four local ones are built in. What you save here replaces or adds to them."
  >
    <template #actions>
      <button type="button" class="primary" data-test="add" @click="open(null)">Add connection</button>
    </template>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="view">
      <table>
        <thead><tr><th>Name</th><th>Type</th><th>Where</th><th>Used by</th><th></th></tr></thead>
        <tbody>
          <tr v-for="row in view.connections" :key="row.name" :data-test="`row-${row.name}`">
            <td><code>{{ row.name }}</code> <span v-if="row.source !== 'saved'" class="tag">{{ row.source }}</span><span v-else class="tag">saved</span></td>
            <td>{{ row.spec.type }}<span v-if="row.spec.allow_raw_sql" class="muted"> · raw SQL</span></td>
            <td>{{ where(row) }}</td>
            <td>{{ row.used_by.length ? row.used_by.join(", ") : "—" }}</td>
            <td class="row-actions">
              <button type="button" class="chip" data-test="edit" @click="open(row)">Edit</button>
              <button v-if="row.source !== 'built-in'" type="button" class="danger" data-test="remove" @click="removing = row">{{ row.source === "changed" ? "Use the built-in" : "Remove" }}</button>
            </td>
          </tr>
        </tbody>
      </table>

      <form v-if="editing !== null" class="card" data-test="form" @submit.prevent="save">
        <h2 class="title">{{ isNew ? "Add connection" : `Edit ${editing}` }}</h2>
        <div class="field">
          <label for="c-name">Name</label>
          <input id="c-name" v-model="name" :disabled="!isNew || busy" autocomplete="off" spellcheck="false" data-test="name" />
          <p class="help">Lowercase letters, digits and _. Saving a built-in name replaces that connection.</p>
        </div>
        <div class="field">
          <label for="c-type">Type</label>
          <select id="c-type" v-model="type" :disabled="busy" data-test="type">
            <option value="sqlite">SQLite file</option>
            <option value="postgres">Postgres</option>
            <option value="firestore">Firestore</option>
          </select>
        </div>
        <div v-if="type === 'sqlite'" class="field">
          <label for="c-path">File</label>
          <input id="c-path" v-model="path" :disabled="busy" autocomplete="off" spellcheck="false" placeholder="reports.db" data-test="path" />
          <p class="help">Relative to Treasury's data folder.</p>
        </div>
        <template v-if="type === 'postgres'">
          <div class="field">
            <label for="c-dsn">Address</label>
            <input id="c-dsn" v-model="dsn" :disabled="busy" autocomplete="off" spellcheck="false" placeholder="${POSTGRES_DSN}" data-test="dsn" />
            <p class="help">A placeholder such as ${POSTGRES_DSN}. Put the real address in Treasury's .env under that name.</p>
          </div>
          <div class="field">
            <label for="c-pool">Pool size (optional)</label>
            <input id="c-pool" v-model="poolSize" type="number" min="1" :disabled="busy" data-test="pool" />
          </div>
        </template>
        <template v-if="type === 'firestore'">
          <div class="field"><label for="c-project">Project (optional)</label><input id="c-project" v-model="project" :disabled="busy" autocomplete="off" data-test="project" /></div>
          <div class="field"><label for="c-cred">Credentials file (optional)</label><input id="c-cred" v-model="credentials" :disabled="busy" autocomplete="off" data-test="credentials" /></div>
          <div class="field"><label for="c-db">Database (optional)</label><input id="c-db" v-model="database" :disabled="busy" autocomplete="off" data-test="database" /></div>
        </template>
        <label class="check"><input v-model="rawSql" type="checkbox" :disabled="busy" data-test="raw-sql" /> Allow raw SQL on this connection</label>
        <div class="field">
          <label for="c-cache">Cache for this connection (seconds, optional)</label>
          <input id="c-cache" v-model="cacheTtl" type="number" min="0" :disabled="busy" data-test="cache" />
          <p class="help">Empty uses the cache defaults below. 0 turns the cache off for this connection.</p>
        </div>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="actions">
          <button type="button" class="chip" :disabled="busy" @click="close">Cancel</button>
          <button type="submit" class="primary" data-test="save" :disabled="busy || !name.trim()">{{ busy ? "Saving…" : "Save" }}</button>
        </div>
      </form>

      <form class="card" data-test="cache-form" @submit.prevent="submitCache">
        <h2 class="title">Cache defaults <span v-if="view.default_cache_stored" class="tag">changed</span></h2>
        <p class="help">What a connection uses when it sets no cache of its own. Used from Treasury's next start.</p>
        <div class="field"><label for="d-ttl">Keep an entry for (seconds)</label><input id="d-ttl" v-model="cacheTtlDefault" type="number" min="0" :disabled="busy" data-test="default-ttl" /></div>
        <div class="field"><label for="d-max">Most entries</label><input id="d-max" v-model="cacheEntries" type="number" min="0" :disabled="busy" data-test="default-entries" /></div>
        <div class="field"><label for="d-neg">Remember a missing record for (seconds)</label><input id="d-neg" v-model="cacheNegative" type="number" min="0" :disabled="busy" data-test="default-negative" /></div>
        <div class="actions">
          <button v-if="view.default_cache_stored" type="button" class="chip" :disabled="busy" data-test="cache-reset" @click="saveCache(null)">Use the built-in defaults</button>
          <button type="submit" class="primary" data-test="cache-save" :disabled="busy || !cacheChanged">Save</button>
        </div>
      </form>
    </template>

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
.card { display: grid; gap: 12px; max-width: 560px; margin-top: 16px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.tag { margin-left: 6px; padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; font-weight: 400; color: var(--muted); }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .field > select { width: 100%; min-width: 0; min-height: 44px; }
.check { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.actions, .row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions { justify-content: flex-end; }
</style>
