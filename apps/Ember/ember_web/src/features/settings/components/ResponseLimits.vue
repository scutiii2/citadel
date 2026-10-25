<script setup lang="ts">
import SettingRow from "../../../components/ui/forms/SettingRow.vue";
import { computed, onMounted, ref } from "vue";
import { tuningClient, type AccountLimits, type Limits } from "../../../api/navigation/TuningClient";
import { errorMessage } from "../../../utils/errors";

/** Two caps for the user's own answers. They only lower what the admin allows, so each box's
 * maximum is the admin's current value. Empty = use the admin's value. */
const FIELDS = [
  { id: "max_output_tokens", label: "Longest answer", unit: "tokens", hint: "The most one reply may use." },
  { id: "max_tool_rounds", label: "Most tool rounds", unit: "rounds", hint: "How many times the agent may use tools before it must answer." },
] as const;

const stored = ref<AccountLimits | null>(null);
const draft = ref<Record<string, string>>({});
const error = ref("");
const saving = ref(false);

const text = (value: number | null): string => (value === null ? "" : String(value));

function adopt(value: AccountLimits): void {
  stored.value = value;
  draft.value = Object.fromEntries(FIELDS.map((f) => [f.id, text(value.limits[f.id])]));
}

const dirty = computed(() => stored.value !== null && FIELDS.some((f) => draft.value[f.id] !== text(stored.value!.limits[f.id])));
const anySet = computed(() => stored.value !== null && FIELDS.some((f) => stored.value!.limits[f.id] !== null));

function payload(): Limits {
  const value = (id: string): number | null => (draft.value[id] === "" ? null : Number(draft.value[id]));
  return { max_output_tokens: value("max_output_tokens"), max_tool_rounds: value("max_tool_rounds") };
}

async function run(action: () => Promise<void>): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    await action();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

const save = () => run(async () => adopt(await tuningClient.save(payload())));
const clear = () => run(async () => {
  await tuningClient.reset();
  adopt({ limits: { max_output_tokens: null, max_tool_rounds: null }, ceiling: stored.value!.ceiling });
});

onMounted(() => run(async () => adopt(await tuningClient.get())));
</script>

<template>
  <fieldset v-if="stored" class="response-limits" :disabled="saving" :aria-busy="saving">
    <SettingRow v-for="field in FIELDS" :key="field.id" :setting-id="field.id" :label="field.label"
      :description="`${field.hint} ${stored.ceiling[field.id] !== null ? 'The most you can set is ' + stored.ceiling[field.id] + '.' : 'The admin limit is currently unavailable.'}`"
      :modified="stored.limits[field.id] !== null" @reset="draft[field.id] = ''">
      <input :id="`limit-${field.id}`" :value="draft[field.id]" :aria-label="field.label" :data-field="field.id" type="number" inputmode="numeric"
        min="1" :max="stored.ceiling[field.id] ?? undefined" step="1" placeholder="Default"
        @input="draft[field.id] = ($event.target as HTMLInputElement).value" />
      <span class="muted">{{ field.unit }}</span>
    </SettingRow>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button type="button" data-test="clear" :disabled="!anySet || saving" @click="clear">Use defaults</button>
      <button type="button" class="primary" data-test="save" :disabled="!dirty || saving" :aria-busy="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
    </div>
  </fieldset>
  <p v-else-if="error" class="error" role="alert">{{ error }}</p>
  <p v-else class="muted" role="status">Loading response limits…</p>
</template>

<style scoped>
.response-limits { padding: 0; margin: 0; min-width: 0; border: none; }
input[type="number"] { max-width: 9em; min-width: 0; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; padding: 10px 0; }
button { padding: 6px 16px; border: 1px solid var(--border); border-radius: var(--radius-full); color: var(--text); background: transparent; cursor: pointer; font: inherit; }
button.primary { border-color: var(--accent); background: var(--accent); color: var(--accent-contrast); font-weight: 600; }
button:disabled { opacity: 0.5; cursor: default; }
.muted { color: var(--muted); }
.error { color: var(--danger); }
</style>
