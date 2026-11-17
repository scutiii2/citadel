<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import { errorMessage } from "../utils/errors";

/** Where Legion reaches Treasury, which keeps its gateway settings. Saved in Legion's own database and used by its next
 * request. Until one is saved, the DB_GATEWAY_URL environment variable (Docker Compose sets it) or the local address is used. */
const savedUrl = ref("");
const stored = ref(false);
const url = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const changed = computed(() => url.value.trim() !== savedUrl.value);

function apply(view: { url: string; stored: boolean }) {
  savedUrl.value = url.value = view.url;
  stored.value = view.stored;
}

onMounted(async () => {
  try {
    apply(await agentsAdminClient.treasuryAddress());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

async function save(value: string | null, done: string) {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await agentsAdminClient.setTreasuryAddress(value));
    notice.value = done;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="card" aria-labelledby="treasury-title">
    <h2 id="treasury-title" class="title">Treasury</h2>
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="fields" data-test="form" @submit.prevent="save(url.trim(), 'Saved. Legion uses it from its next request.')">
      <div class="field">
        <label for="treasury-url">Address</label>
        <input id="treasury-url" v-model="url" type="url" inputmode="url" autocomplete="off" spellcheck="false" required :disabled="saving" data-test="url" />
        <p class="help">For example http://treasury:29602 inside Docker. {{ stored ? "Saved here." : "Not saved here: the environment's or the default address is in use." }}</p>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="notice" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button v-if="stored" type="button" class="chip" :disabled="saving" data-test="reset" @click="save(null, 'Back to the default. Legion uses it from its next request.')">Use the default</button>
        <button type="submit" class="primary" data-test="save" :disabled="saving || !changed">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.card { display: grid; gap: 12px; max-width: 560px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.fields { display: grid; gap: 16px; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.error { margin: 0; color: var(--danger); }
.notice, .muted { margin: 0; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
</style>
