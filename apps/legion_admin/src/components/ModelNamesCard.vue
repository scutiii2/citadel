<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { agentsAdminClient, type ModelName } from "../api/AgentsAdminClient";
import { errorMessage } from "../utils/errors";

/** The model names gateway presets leave open: Azure deployment names and vLLM served model names. Saved in Legion's
 * database. A saved name wins over the environment's; an agent uses a change when it next starts. */
const models = ref<ModelName[]>([]);
const edits = ref<Record<string, string>>({});
const removing = ref<Set<string>>(new Set());
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const changes = computed(() => {
  const out: Record<string, string | null> = {};
  for (const model of models.value) {
    if (removing.value.has(model.name)) out[model.name] = null;
    else if (model.name in edits.value && edits.value[model.name].trim() !== model.value) out[model.name] = edits.value[model.name].trim();
  }
  return out;
});
const changed = computed(() => Object.keys(changes.value).length > 0);

function apply(list: ModelName[]) {
  models.value = list;
  edits.value = Object.fromEntries(list.map((model) => [model.name, model.value]));
  removing.value = new Set();
}

function toggleRemove(name: string) {
  const next = new Set(removing.value);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  removing.value = next;
}

onMounted(async () => {
  try {
    apply(await agentsAdminClient.modelNames());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await agentsAdminClient.setModelNames(changes.value));
    notice.value = "Saved. Each agent uses it when it next starts.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="card" aria-labelledby="model-names-title">
    <h2 id="model-names-title" class="title">Model names</h2>
    <p class="help">Names that a gateway preset leaves open. A preset with an empty name leaves that model out.</p>
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="fields" data-test="form" @submit.prevent="save">
      <div v-for="model in models" :key="model.name" class="field" :data-test="`row-${model.name}`">
        <label :for="`m-${model.name}`">{{ model.name }}</label>
        <input
          :id="`m-${model.name}`"
          v-model="edits[model.name]"
          :disabled="saving || removing.has(model.name)"
          autocomplete="off"
          spellcheck="false"
          data-test="input"
        />
        <button v-if="model.stored" type="button" class="chip" data-test="remove" :disabled="saving" @click="toggleRemove(model.name)">
          {{ removing.has(model.name) ? "Keep it" : "Remove the saved name" }}
        </button>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="notice" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="saving || !changed">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.card { display: grid; gap: 12px; max-width: 560px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.fields { display: grid; gap: 16px; }
.field { display: grid; gap: 4px; min-width: 0; justify-items: start; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.error { margin: 0; color: var(--danger); }
.notice, .muted { margin: 0; color: var(--muted); }
.actions { display: flex; justify-content: flex-end; }
</style>
