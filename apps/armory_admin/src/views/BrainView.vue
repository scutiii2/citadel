<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { brainClient, type BrainConnection, type ConnectionDraft } from "../api/BrainClient";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import { errorMessage } from "../utils/errors";

const saved = ref<BrainConnection | null>(null);
const draft = reactive<ConnectionDraft>({
  label: "", endpoint: "", folder: "Inbox", enabled: true, allow_write: false, expected_revision: 0,
});
const key = ref("");
const busy = ref(false);
const confirming = ref(false);
const error = ref("");
const notice = ref("");
const settings = ["label", "endpoint", "folder", "enabled", "allow_write"] as const;
const dirty = computed(() => saved.value !== null &&
  (key.value !== "" || settings.some(name => draft[name] !== saved.value?.[name])));

function apply(row: BrainConnection) {
  const { label, endpoint, folder, enabled, allow_write, revision, status, credential_configured } = row;
  saved.value = { label, endpoint, folder, enabled, allow_write, revision, status, credential_configured };
  Object.assign(draft, { label, endpoint, folder, enabled, allow_write, expected_revision: revision });
  key.value = "";
}

async function run(operation: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await operation();
  } catch (cause) {
    error.value = errorMessage(cause);
  } finally {
    busy.value = false;
  }
}

const load = () => run(async () => apply(await brainClient.connection()));
onMounted(load);

function input(): ConnectionDraft {
  return { ...draft, ...(key.value ? { api_key: key.value } : {}) };
}

const save = () => run(async () => {
  apply(await brainClient.save(input()));
  notice.value = "Connection saved";
});
const test = () => run(async () => {
  notice.value = (await brainClient.test(input())).message ?? "Connection test succeeded";
});
const check = () => run(async () => {
  const status = await brainClient.status();
  notice.value = `Connection: ${status.status ?? "unknown"}. Index: ${status.index_status ?? "not_started"}.`;
});
const disable = () => run(async () => {
  confirming.value = false;
  apply(await brainClient.disable(draft.expected_revision));
  notice.value = "Connection disabled";
});
</script>

<template>
  <PageLayout title="Brain" description="Every signed-in user can read the shared vault. Publishing requires permission.">
    <section class="brain-connection" aria-label="Instance Brain" :aria-busy="busy">
      <h3>Instance Brain</h3>
      <p class="muted">Use an HTTPS Obsidian Local REST API endpoint reachable from the Citadel server.</p>
      <p v-if="saved" class="muted">
        Status: {{ saved.status }} · {{ saved.credential_configured ? "API key configured" : "No managed API key" }}
      </p>
      <form v-if="saved" @submit.prevent="save">
        <fieldset :disabled="busy">
          <label>Label<input v-model="draft.label" name="label" required maxlength="80" autocomplete="off" /></label>
          <label>HTTPS endpoint<input v-model="draft.endpoint" type="url" required maxlength="1000" autocomplete="off" /></label>
          <label>
            API key
            <input v-model="key" type="password" autocomplete="new-password" maxlength="4096" aria-describedby="brain-key-hint" />
            <small id="brain-key-hint" class="muted">Leave blank to keep the saved key for this origin.</small>
          </label>
          <label>Default publication folder<input v-model="draft.folder" maxlength="240" /></label>
          <ToggleSwitch :checked="draft.enabled" @change="draft.enabled = ($event.target as HTMLInputElement).checked">
            Enable connection
          </ToggleSwitch>
          <ToggleSwitch :checked="draft.allow_write" @change="draft.allow_write = ($event.target as HTMLInputElement).checked">
            Allow publishing to this vault
          </ToggleSwitch>
          <p class="muted">Test connection only reads the candidate vault. Changes apply after Save.</p>
          <div class="actions">
            <button class="brain-action primary" type="submit" :disabled="!dirty">Save connection</button>
            <button class="brain-action" type="button" @click="test">Test connection</button>
            <button class="brain-action" type="button" :disabled="!saved.enabled" @click="check">Check saved status</button>
          </div>
        </fieldset>
      </form>
      <p v-if="dirty" class="muted">Unsaved connection changes</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" role="status">{{ notice }}</p>
      <button v-if="error && !saved" class="brain-action" type="button" :disabled="busy" @click="load">Retry</button>
    </section>
    <section v-if="saved?.enabled" class="disable-section" aria-label="Disable Instance Brain">
      <button class="brain-action disable" type="button" :disabled="busy" @click="confirming = true">Disable connection</button>
    </section>
    <ConfirmModal :open="confirming" title="Disable Instance Brain?" :danger="true"
      message="Signed-in users will lose access to the shared vault until it is enabled again. Unsaved edits will be discarded."
      confirm-label="Disable connection" :busy="busy" @confirm="disable" @close="confirming = false" />
  </PageLayout>
</template>

<style scoped>
.brain-connection { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; background: var(--surface); }
.brain-connection h3 { margin: 0; }
fieldset { border: 0; margin: 0; padding: 0; display: grid; gap: 12px; min-width: 0; }
fieldset > label { display: grid; gap: 4px; }
input { width: 100%; box-sizing: border-box; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); padding: 8px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
button.brain-action { border: 1px solid var(--border); border-radius: var(--radius-full); padding: 7px 12px; background: var(--surface); color: var(--text); cursor: pointer; }
button.brain-action.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-contrast); }
button.brain-action:disabled { opacity: .55; cursor: default; }
.muted { color: var(--muted); font-size: .9em; }
.error { color: var(--danger); }
.disable-section { margin-top: 16px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-lg); }
button.brain-action.disable { color: var(--danger); border-color: var(--danger); }
</style>
