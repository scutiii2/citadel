<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { GatewaySettingsView } from "../api/AgentsAdminClient";
import PasswordInput from "./PasswordInput.vue";
import { errorMessage } from "../utils/errors";

/** Address and access token of one service Legion calls. Saved in the database, not in a file.
 * The token is write-only: the server only says whether one is set. */
const props = defineProps<{
  /** Unique on the page; prefixes the field ids. */
  id: string;
  title: string;
  example: string;
  load: () => Promise<GatewaySettingsView>;
  store: (changes: { url?: string; token?: string }) => Promise<GatewaySettingsView>;
}>();

const savedUrl = ref("");
const url = ref("");
const token = ref("");
const hasToken = ref(false);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const changed = computed(() => url.value.trim() !== savedUrl.value || token.value !== "");

function apply(view: { url: string; has_token: boolean }) {
  savedUrl.value = url.value = view.url;
  hasToken.value = view.has_token;
  token.value = "";
}

onMounted(async () => {
  try {
    apply(await props.load());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

/** Sends only what changed, so an untouched token field keeps the stored token. */
async function save(changes: { url?: string; token?: string }, done: string) {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await props.store(changes));
    notice.value = done;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

function submit() {
  const changes: { url?: string; token?: string } = {};
  if (url.value.trim() !== savedUrl.value) changes.url = url.value.trim();
  if (token.value) changes.token = token.value;
  void save(changes, "Saved. Agents use the new values within half a minute.");
}
</script>

<template>
  <section class="card" :aria-labelledby="`${id}-title`">
    <h2 :id="`${id}-title`" class="title">{{ title }}</h2>
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="fields" @submit.prevent="submit">
      <div class="field">
        <label :for="`${id}-url`">Address</label>
        <input
          :id="`${id}-url`"
          v-model="url"
          type="url"
          inputmode="url"
          autocomplete="off"
          spellcheck="false"
          required
          data-test="url"
          :disabled="saving"
          :aria-describedby="`${id}-url-help`"
        />
        <p :id="`${id}-url-help`" class="help">For example {{ example }} inside Docker.</p>
      </div>

      <div class="field">
        <PasswordInput
          v-model="token"
          label="Access token"
          autocomplete="off"
          data-test="token"
          :disabled="saving"
          :placeholder="hasToken ? 'Leave empty to keep the saved token' : 'Paste the token made for Legion'"
          :aria-describedby="`${id}-token-help`"
        />
        <p :id="`${id}-token-help`" class="help" data-test="token-state">
          {{ hasToken ? "A token is saved. It is never shown again." : "No token is saved yet." }}
          Make one on the service's admin page, under Access tokens.
        </p>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="notice" role="status" data-test="notice">{{ notice }}</p>

      <div class="actions">
        <button
          v-if="hasToken"
          type="button"
          class="chip"
          data-test="clear-token"
          :disabled="saving"
          @click="save({ token: '' }, 'Token removed.')"
        >Remove token</button>
        <button type="submit" class="primary" data-test="save" :disabled="saving || !changed">
          {{ saving ? "Saving…" : "Save" }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.card {
  display: grid;
  gap: 12px;
  max-width: 560px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.title { margin: 0; font-size: 1em; font-weight: 600; }
.fields { display: grid; gap: 16px; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
}
.field > input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.error { margin: 0; color: var(--danger); }
.notice { margin: 0; color: var(--muted); }
</style>
