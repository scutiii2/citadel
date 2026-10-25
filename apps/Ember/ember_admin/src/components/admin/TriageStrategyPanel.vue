<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { triageStrategyClient, type TriageStrategyInfo } from "../../api/TriageStrategyClient";
import { errorMessage } from "../../utils/errors";
import "./admin.css";

/** Whether a default is set, for a page that counts changed settings. */
const emit = defineEmits<{ modified: [value: boolean] }>();

const NOT_SET = "";
const info = ref<TriageStrategyInfo | null>(null);
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);
const draft = ref(NOT_SET);

const stored = computed(() => info.value?.default ?? NOT_SET);
const dirty = computed(() => info.value !== null && draft.value !== stored.value);
const choices = computed(() => {
  const names = info.value?.strategies ?? [];
  // A default the service no longer lists stays visible so the admin can see and replace it.
  return stored.value && !names.includes(stored.value) ? [stored.value, ...names] : names;
});

async function load(): Promise<void> {
  loadError.value = "";
  try {
    info.value = await triageStrategyClient.get();
    draft.value = stored.value;
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

function cancel(): void {
  draft.value = stored.value;
  saveError.value = "";
}

async function save(): Promise<void> {
  if (saving.value || !dirty.value) return;
  saveError.value = "";
  saving.value = true;
  try {
    info.value = await triageStrategyClient.set(draft.value === NOT_SET ? null : draft.value);
    draft.value = stored.value;
    saved.value = true;
  } catch (err) {
    // The draft stays, so Save can be retried or Cancel drops it.
    saveError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

watch(stored, (value) => emit("modified", value !== NOT_SET), { immediate: true });
onMounted(load);
</script>

<template>
  <div class="admin-panel">
    <p v-if="loadError" class="error" role="alert">error: {{ loadError }}</p>
    <section class="card">
      <div class="head">
        <span v-if="stored !== NOT_SET" class="dot" title="Changed from the default" aria-hidden="true" />
        <h3>Triage strategy</h3>
        <span v-if="saved && !dirty" class="chip saved">Saved</span>
        <span class="chip scope">Applies to every Laya caller</span>
      </div>
      <label class="field">
        <span>Default strategy</span>
        <select v-model="draft" :disabled="saving || !info || info.strategies.length === 0" aria-label="Default triage strategy" @change="saved = false">
          <option :value="NOT_SET">Not set (follows triage_order)</option>
          <option v-for="name in choices" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <p class="muted">
        The decision strategy the Laya service uses when a request names none. Accounts can pick their own for prompts
        they send straight to the Triage Assistant from Ember. "Not set" keeps today's behaviour: the strategy follows
        the order and switches in config_tuning.json.
      </p>
      <div v-if="dirty" class="save-bar" role="group" aria-label="Unsaved change">
        <span class="dot" aria-hidden="true" />
        <span class="msg">You have an unsaved change. It applies to every account that has not picked its own.</span>
        <button type="button" class="small" :disabled="saving" @click="cancel">Cancel</button>
        <button type="button" class="primary" :disabled="saving" :aria-busy="saving" @click="save">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
      <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
    </section>
  </div>
</template>

<style scoped>
.card {
  padding: 20px;
  background: var(--bg);
}
.card > .muted {
  max-width: 620px;
  font-size: 0.9em;
}
.card h3 {
  margin: 0;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
}
.chip.scope {
  margin-left: auto;
}
.chip.saved {
  color: var(--success);
  border-color: var(--success);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 320px;
  margin-bottom: 12px;
}
.field select {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--surface);
  font: inherit;
}
.save-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.save-bar .msg {
  flex: 1 1 200px;
  font-size: 0.9em;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.card p {
  margin-bottom: 0;
}
</style>
