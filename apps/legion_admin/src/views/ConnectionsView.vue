<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import PageLayout from "../components/PageLayout.vue";
import PasswordInput from "../components/PasswordInput.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** Where Legion reaches ConversationGateway. Saved in the database, not in a file.
 * The token is write-only: the server only says whether one is set. */
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
    apply(await agentsAdminClient.gatewaySettings());
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
    apply(await agentsAdminClient.setGatewaySettings(changes));
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
  <PageLayout
    class="info-content connections"
    title="Connections"
    description="Where Legion reaches ConversationGateway, the service that holds the model provider keys."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="card" @submit.prevent="submit">
      <div class="field">
        <label for="gateway-url">Gateway address</label>
        <input
          id="gateway-url"
          v-model="url"
          type="url"
          inputmode="url"
          autocomplete="off"
          spellcheck="false"
          required
          data-test="url"
          :disabled="saving"
          aria-describedby="gateway-url-help"
        />
        <p id="gateway-url-help" class="help">For example http://conversationgateway:29407 inside Docker.</p>
      </div>

      <div class="field">
        <PasswordInput
          v-model="token"
          label="Access token"
          autocomplete="off"
          data-test="token"
          :disabled="saving"
          :placeholder="hasToken ? 'Leave empty to keep the saved token' : 'Paste the token made for Legion'"
          aria-describedby="gateway-token-help"
        />
        <p id="gateway-token-help" class="help" data-test="token-state">
          {{ hasToken ? "A token is saved. It is never shown again." : "No token is saved yet." }}
          Make one on the gateway's admin page, under Access tokens.
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
  </PageLayout>
</template>

<style scoped>
.card {
  display: grid;
  gap: 16px;
  max-width: 560px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
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
