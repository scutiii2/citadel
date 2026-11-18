<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { brainsClient, type BrainConnection, type BrainScope, type ConnectionDraft } from "../api/BrainsClient";
import ToggleSwitch from "./ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";

const props = defineProps<{ scope: BrainScope }>();
const saved = ref<BrainConnection | null>(null);
const draft = reactive<ConnectionDraft>({ label: "", endpoint: "", folder: "Inbox", enabled: true, allow_write: false, expected_revision: 0 });
const key = ref("");
const busy = ref(false);
const error = ref("");
const notice = ref("");
const title = computed(() => props.scope === "instance" ? "Instance Brain" : "Personal Brain");
const dirty = computed(() => saved.value && (key.value || ["label", "endpoint", "folder", "enabled", "allow_write"].some(
  name => draft[name as keyof ConnectionDraft] !== saved.value![name as keyof BrainConnection])));
function apply(row: BrainConnection) {
  saved.value = row;
  Object.assign(draft, { label: row.label, endpoint: row.endpoint, folder: row.folder,
    enabled: row.enabled, allow_write: row.allow_write, expected_revision: row.revision });
  key.value = "";
}
onMounted(async () => {
  busy.value = true;
  try { apply(await brainsClient.connection(props.scope)); } catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
});
async function act(action: "save" | "test" | "disable" | "status") {
  if (busy.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  const body = { ...draft, ...(key.value ? { api_key: key.value } : {}), ...(action === "disable" ? { enabled: false } : {}) };
  try {
    if (action === "status") {
      const status = await brainsClient.browse(props.scope, "status");
      notice.value = `Connection: ${status.status ?? "unknown"}. Index: ${status.index_status ?? "not_started"}.`;
    } else if (action === "test") notice.value = (await brainsClient.test(props.scope, body)).message ?? "Connection test succeeded";
    else { apply(await brainsClient.save(props.scope, body)); notice.value = action === "disable" ? "Connection disabled" : "Connection saved"; }
  } catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
}
</script>
<template>
  <section class="brain-connection" :aria-label="title" :aria-busy="busy">
    <h3>{{ title }}</h3>
    <p>{{ scope === "instance" ? "Every signed-in user can read this vault. Publishing requires permission." : "Your durable knowledge, available only to your account." }}</p>
    <p class="muted">Use an HTTPS Obsidian Local REST API endpoint reachable from the Citadel server. A desktop loopback address cannot connect a remote server to your computer.</p>
    <p v-if="saved" class="muted">Status: {{ saved.status }} · {{ saved.credential_configured ? "API key configured" : "No managed API key" }}</p>
    <fieldset :disabled="busy || !saved">
      <label>Label<input v-model="draft.label" maxlength="80" autocomplete="off" /></label>
      <label>HTTPS endpoint<input v-model="draft.endpoint" type="url" placeholder="https://vault.example:27124" autocomplete="off" /></label>
      <label>API key<input v-model="key" type="password" autocomplete="new-password" :placeholder="saved?.credential_configured ? 'Leave unchanged to keep the saved key' : 'Obsidian API key'" /></label>
      <label>Default publication folder<input v-model="draft.folder" maxlength="240" /></label>
      <ToggleSwitch :checked="draft.enabled" @change="draft.enabled = ($event.target as HTMLInputElement).checked">Enable connection</ToggleSwitch>
      <ToggleSwitch :checked="draft.allow_write" @change="draft.allow_write = ($event.target as HTMLInputElement).checked">Allow publishing to this vault</ToggleSwitch>
      <p class="muted">Changes apply after Save. Test connection only reads the candidate vault.</p>
      <div class="actions">
        <button type="button" :disabled="!dirty" @click="act('save')">{{ busy ? "Working…" : "Save connection" }}</button>
        <button type="button" @click="act('test')">Test connection</button>
        <button type="button" :disabled="!saved?.enabled" @click="act('status')">Check saved status</button>
        <button type="button" :disabled="!saved?.enabled || !saved?.revision" @click="act('disable')">Disable connection</button>
      </div>
    </fieldset>
    <p v-if="dirty" class="muted">Unsaved connection changes</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
  </section>
</template>
<style scoped>
.brain-connection { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; background: var(--surface); margin-bottom: 16px; }
fieldset { border: 0; padding: 0; display: grid; gap: 12px; min-width: 0; }
label { display: grid; gap: 4px; }
input { width: 100%; box-sizing: border-box; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); padding: 8px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
button { border: 1px solid var(--border); border-radius: var(--radius-full); padding: 7px 12px; background: var(--surface); color: var(--text); cursor: pointer; }
button:first-child { background: var(--accent); color: var(--accent-contrast); }
button:disabled { opacity: .55; cursor: default; }
.muted { color: var(--muted); font-size: .9em; }
.error { color: var(--danger); }
</style>
