<script setup lang="ts">
import SettingRow from "../../../components/ui/forms/SettingRow.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { tuningClient, type AccountLimits } from "../../../api/navigation/TuningClient";
import { adoptLimits, emptyLimitsState, limitsDirty, limitsPayload, type ResponseLimitsState } from "../utils/responseLimits";
import { errorMessage } from "../../../utils/errors";

/** Two caps for the user's own answers. They only lower what the admin allows, so each box's
 * maximum is the admin's current value. Empty = use the admin's value. */
const FIELDS = [
  { id: "max_output_tokens", label: "Longest answer", unit: "tokens", hint: "The most one reply may use." },
  { id: "max_tool_rounds", label: "Most tool rounds", unit: "rounds", hint: "How many times the agent may use tools before it must answer." },
] as const;

const state = defineModel<ResponseLimitsState>({ default: () => reactive(emptyLimitsState()) });
const stored = computed(() => state.value.stored);
const draft = computed(() => state.value.draft);
const error = ref("");
const saving = computed(() => state.value.pending);
const dirty = computed(() => limitsDirty(state.value));
const anySet = computed(() => stored.value !== null && FIELDS.some(f => stored.value!.limits[f.id] !== null));

function adopt(value: AccountLimits, owner: ResponseLimitsState): void {
  if (state.value === owner) Object.assign(owner, adoptLimits(value));
}
async function run(action: (owner: ResponseLimitsState) => Promise<void>): Promise<void> {
  const owner = state.value;
  if (owner.pending) return;
  owner.pending = true;
  error.value = "";
  try { await action(owner); }
  catch (err) { if (state.value === owner) error.value = errorMessage(err); }
  finally { owner.pending = false; }
}
const save = () => run(async owner => adopt(await tuningClient.save(limitsPayload(owner.draft)), owner));
const clear = () => run(async owner => {
  await tuningClient.reset();
  adopt({ limits: { max_output_tokens: null, max_tool_rounds: null }, ceiling: owner.stored!.ceiling }, owner);
});
onMounted(() => { if (!stored.value) void run(async owner => adopt(await tuningClient.get(), owner)); });
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
