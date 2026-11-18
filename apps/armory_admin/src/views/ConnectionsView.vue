<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import PageLayout from "../components/PageLayout.vue";
import BaseModal from "../components/BaseModal.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { connectionsClient, type AuthKind, type ConnectionInfo, type Service, type TestResult, type Transport } from "../api/ConnectionsClient";
import { adminAppUrl } from "../utils/siblings";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

const transports = ["mcp", "rest"] as const;
const services = ["portcullis", "stronghold", "legion", "armory", "treasury"] as const;
const features: Record<string, string> = { bard: "Read aloud", scribe: "Dictation and audio attachments", reader: "Document attachments" };
const records = ref<ConnectionInfo[]>([]);
const count = ref<number | null>(null);
const loading = ref(true);
const error = ref("");
const busy = ref(false);
const editError = ref("");
const results = ref<Record<string, TestResult>>({});
const testing = ref(new Set<string>());
const editing = ref<ConnectionInfo | null>(null);
const removing = ref<ConnectionInfo | null>(null);
const editorOpen = ref(false);
const required = computed(() => records.value.filter(entry => entry.class === "required"));
const optional = computed(() => records.value.filter(entry => entry.class === "server"));
const emberLink = new URL("/capabilities?tab=extensions", import.meta.env.VITE_EMBER_APP_URL || adminAppUrl(26506, window.location.href)).href;

function transportDraft(entry: ConnectionInfo | null, key: Transport) {
  const block = entry?.[key];
  const kind: AuthKind = block?.auth.kind ?? (entry?.class === "required" ? "token" : "none");
  const address = key === "mcp" ? entry?.mcp?.url : entry?.rest?.base_url;
  return { address: address ?? "", kind, credential: "", audience: block?.auth.audience ?? "legion" as Service };
}

function draftFor(entry: ConnectionInfo | null) {
  return { label: entry?.label ?? "", description: entry?.description ?? "", enabled: entry?.enabled ?? true,
    web_url: entry?.web_url ?? "", mcp: transportDraft(entry, "mcp"), rest: transportDraft(entry, "rest") };
}

const draft = ref(draftFor(null));
function edit(entry: ConnectionInfo | null): void {
  editing.value = entry;
  editError.value = "";
  draft.value = draftFor(entry);
  editorOpen.value = true;
}

function closeEditor(): void {
  if (busy.value) return;
  editorOpen.value = false;
  draft.value = draftFor(null);
}

function transportChanges(key: Transport): object | null {
  const fields = draft.value[key];
  if (!fields.address.trim()) return null;
  const auth: Record<string, unknown> = { kind: fields.kind };
  const value = fields.credential.trim();
  if (fields.kind === "token" && value) auth.token = value;
  if (fields.kind === "headers" && value) {
    try {
      auth.headers = JSON.parse(value);
    } catch {
      throw new Error("Enter credential headers as a JSON object.");
    }
  }
  if (fields.kind === "internal") auth.audience = fields.audience;
  return { [key === "mcp" ? "url" : "base_url"]: fields.address.trim(), auth };
}

async function save(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  editError.value = "";
  try {
    const { label, description, enabled, web_url } = draft.value;
    const entry = editing.value;
    const changes = { label, description, enabled, web_url, rest: transportChanges("rest"),
      ...(!entry?.mcp?.local ? { mcp: transportChanges("mcp") } : {}) };
    const saved = entry ? await connectionsClient.update(entry.name, changes) : await connectionsClient.create(changes);
    records.value = entry ? records.value.map(item => item.name === saved.name ? saved : item) : [...records.value, saved];
    for (const transport of transports) delete results.value[saved.name + ":" + transport];
    editorOpen.value = false;
    draft.value = draftFor(null);
  } catch (err) {
    editError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function remove(): Promise<void> {
  if (!removing.value || busy.value) return;
  const entry = removing.value;
  busy.value = true;
  editError.value = "";
  try {
    await connectionsClient.remove(entry.name);
    records.value = records.value.filter(item => item.name !== entry.name);
    removing.value = null;
  } catch (err) {
    editError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function test(entry: ConnectionInfo, transport: Transport): Promise<void> {
  const key = entry.name + ":" + transport;
  if (testing.value.has(key)) return;
  testing.value.add(key);
  try {
    results.value[key] = await connectionsClient.test(entry.name, transport);
  } catch (err) {
    results.value[key] = { ok: false, message: errorMessage(err) };
  } finally {
    testing.value.delete(key);
  }
}

onMounted(async () => {
  void connectionsClient.personalCount().then(value => { count.value = value; }).catch(() => {});
  try {
    records.value = await connectionsClient.list();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <PageLayout class="info-content" title="Connections">
    <p v-if="loading" class="muted" role="status">Loading connections…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="!loading && !error">
      <section v-for="[heading, entries] in ([['Required', required], ['Server-sided optional', optional]] as const)" :key="heading">
        <div class="section-heading">
          <h3>{{ heading }}</h3>
          <button v-if="heading === 'Server-sided optional'" type="button" class="primary" @click="edit(null)">Add connection</button>
        </div>
        <p v-if="heading === 'Server-sided optional' && !entries.length" class="muted">No optional connections.</p>
        <ul v-else class="connection-list">
          <li v-for="entry in entries" :key="entry.name" class="card connection">
            <div class="section-heading">
              <strong>{{ entry.label }}</strong>
              <button type="button" :aria-label="'Edit ' + entry.label" @click="edit(entry)">Edit</button>
            </div>
            <p v-if="features[entry.name]" class="muted">{{ features[entry.name] }}</p>
            <p v-if="entry.description">{{ entry.description }}</p>
            <p v-if="entry.class === 'required' && !entry.ready"><strong>Not connected.</strong> {{ entry.reason }}</p>
            <div v-for="transport in transports" :key="transport" class="transport">
              <div class="section-heading">
                <strong>{{ transport.toUpperCase() }}</strong>
                <button type="button" :aria-label="'Test ' + entry.label + ' ' + transport.toUpperCase()"
                  :disabled="!entry.enabled || !entry[transport] || (transport === 'mcp' && entry.mcp?.local) || testing.has(entry.name + ':' + transport)"
                  :aria-busy="testing.has(entry.name + ':' + transport)" @click="test(entry, transport)">Test</button>
              </div>
              <template v-if="entry[transport]">
                <p class="address">{{ transport === 'mcp' ? entry.mcp?.url || (entry.mcp?.local ? 'Local process' : 'Address unavailable') : entry.rest?.base_url }}</p>
                <p class="muted">
                  {{ entry[transport]?.auth.kind === 'token' ? (entry[transport]?.auth.configured ? 'Token set' : 'Token missing') :
                    entry[transport]?.auth.kind === 'none' ? 'No credentials' :
                    entry[transport]?.auth.configured ? 'Credentials configured' : 'Credentials missing' }}
                  <template v-if="transport === 'mcp' && entry.mcp?.status === 'connected'"> · {{ entry.mcp.tools?.length ?? 0 }} tools</template>
                </p>
                <p v-if="transport === 'mcp' && entry.mcp?.error" class="muted">{{ entry.mcp.error }}</p>
              </template>
              <p v-else class="muted">Not configured</p>
              <div v-if="results[entry.name + ':' + transport]" role="status">
                {{ results[entry.name + ':' + transport]?.message }}
                <ul v-if="results[entry.name + ':' + transport]?.tools?.length">
                  <li v-for="tool in results[entry.name + ':' + transport]?.tools" :key="tool">{{ tool }}</li>
                </ul>
              </div>
            </div>
          </li>
        </ul>
      </section>
      <section>
        <h3>Client-sided</h3>
        <p v-if="count !== null">{{ count }} personal {{ count === 1 ? 'connection' : 'connections' }} for your account.</p>
        <p>Manage your own connections in <a :href="emberLink">Ember → Capabilities → Extensions</a>.</p>
      </section>
    </template>
    <BaseModal :open="editorOpen" :title="editing ? 'Edit ' + editing.label : 'Add connection'" @close="closeEditor">
      <form class="dialog-form connection-form" @submit.prevent="save">
        <label>Name<input v-model="draft.label" required maxlength="120" /></label>
        <label>Description<input v-model="draft.description" maxlength="1000" /></label>
        <label>Website URL<input v-model="draft.web_url" type="url" /></label>
        <ToggleSwitch :checked="draft.enabled" @change="draft.enabled = ($event.target as HTMLInputElement).checked">Enabled</ToggleSwitch>
        <fieldset v-for="transport in transports" :key="transport">
          <legend>{{ transport.toUpperCase() }}</legend>
          <p v-if="transport === 'mcp' && editing?.mcp?.local">Local MCP process managed on the server.</p>
          <template v-else>
            <label>{{ transport === 'mcp' ? 'MCP URL' : 'REST base URL' }}<input v-model="draft[transport].address" type="url" /></label>
            <template v-if="draft[transport].address">
              <label v-if="editing?.class !== 'required' || transport !== 'rest'">Authentication
                <select v-model="draft[transport].kind">
                  <option value="none">None</option><option value="token">Token</option>
                  <option value="headers">Credential headers</option><option value="internal">Signed service assertion</option>
                </select>
              </label>
              <label v-if="draft[transport].kind === 'token' || draft[transport].kind === 'headers'">
                {{ draft[transport].kind === 'token' ? 'Token' : 'Credential headers in JSON' }}
                <input v-model="draft[transport].credential" type="password" autocomplete="new-password" />
                <small v-if="editing?.[transport]?.auth.configured">Leave blank to keep the saved credentials.</small>
              </label>
              <label v-if="draft[transport].kind === 'internal'">Audience
                <select v-model="draft[transport].audience"><option v-for="service in services" :key="service">{{ service }}</option></select>
              </label>
            </template>
          </template>
        </fieldset>
        <p v-if="editError" role="alert" class="error">{{ editError }}</p>
        <button type="submit" class="primary" :disabled="busy" :aria-busy="busy">Save</button>
        <section v-if="editing?.class === 'server'" class="danger-zone">
          <h3>Danger zone</h3>
          <button type="button" class="danger" :disabled="busy" @click="removing = editing; closeEditor(); editError = ''">Remove connection</button>
        </section>
      </form>
    </BaseModal>
    <ConfirmModal :open="removing !== null" title="Remove connection"
      :message="editError || 'Remove ' + removing?.label + ' for every account?'"
      confirm-label="Remove" danger :busy="busy" @confirm="remove" @close="removing = null" />
  </PageLayout>
</template>

<style scoped>
.section-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.connection-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(265px, 100%), 1fr)); gap: 12px; padding: 0; list-style: none; }
.connection { min-width: 0; overflow-wrap: anywhere; }
.transport { border-top: 1px solid var(--border); margin-top: 12px; padding-top: 8px; }
.address { font-family: var(--mono); }
.connection-form fieldset { border: 1px solid var(--border); border-radius: var(--radius-md); min-width: 0; }
.connection-form label { display: grid; gap: 4px; }
</style>
