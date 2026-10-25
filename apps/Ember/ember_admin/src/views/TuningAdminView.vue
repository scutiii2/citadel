<script setup lang="ts">
import { computed, getCurrentInstance, onMounted, onUnmounted, ref } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import SettingRow from "../components/SettingRow.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import PageLayout from "../components/PageLayout.vue";
import { tuningClient, type TuningChanges, type TuningView } from "../api/TuningClient";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** One editable value: where it lives in config_tuning.json, how to label it, and its bounds
 * (the same ones garrison enforces; garrison's answer is what the page shows on a refusal). */
interface Field {
  path: string;
  label: string;
  kind: "int" | "number" | "bool";
  unit?: string;
  min?: number;
  max?: number;
}
interface Group { id: string; title: string; note: string; fields: Field[] }

const VOTERS = ["laya-english", "laya-typed", "jev"];
const KINDS = ["choice", "noul", "score"];

const GROUPS: Group[] = [
  {
    id: "limits", title: "Token limits", note: "The default for every provider. A user can set a lower value of their own for output and tool rounds.",
    fields: [
      { path: "token_limits.default.max_output_tokens", label: "Max output tokens", kind: "int", min: 1, max: 200000 },
      { path: "token_limits.default.max_context_tokens", label: "Max context tokens", kind: "int", min: 1000, max: 2000000 },
      { path: "token_limits.default.max_tool_rounds", label: "Max tool rounds", kind: "int", min: 1, max: 100 },
    ],
  },
  {
    id: "failover", title: "Gateway failover", note: "How long a failing gateway is skipped before it is tried again.",
    fields: [
      { path: "gateway_failover.quota_cooldown_seconds", label: "After a quota error", kind: "number", unit: "s", min: 0, max: 604800 },
      { path: "gateway_failover.auth_cooldown_seconds", label: "After an auth error", kind: "number", unit: "s", min: 0, max: 604800 },
      { path: "gateway_failover.unavailable_cooldown_seconds", label: "After an outage", kind: "number", unit: "s", min: 0, max: 604800 },
    ],
  },
  {
    id: "classifier", title: "Classifier", note: "Changes how questions are routed. Nothing checks the result of an edit, so change one value at a time.",
    fields: [
      { path: "classifier.timeout_seconds", label: "Timeout", kind: "number", unit: "s", min: 0.1, max: 60 },
      { path: "classifier.max_input_chars", label: "Max input characters", kind: "int", min: 1, max: 1000000 },
      { path: "classifier.triage_window", label: "Triage window", kind: "int", min: 512, max: 32768 },
      { path: "classifier.triage_prune_ratio", label: "Prune ratio", kind: "number", min: 0, max: 0.99 },
      { path: "classifier.triage_pair_ratio", label: "Pair ratio", kind: "number", min: 0.01, max: 1 },
      { path: "classifier.triage_fallback", label: "Use the fallback classifier", kind: "bool" },
      { path: "classifier.triage_trace", label: "Trace decisions", kind: "bool" },
    ],
  },
  {
    id: "thresholds", title: "Confidence thresholds", note: "A voter's answer counts only above this confidence. 2 = two options, 3+ = three or more.",
    fields: ["2", "3+"].flatMap((count) => VOTERS.map((voter): Field => ({
      path: `classifier.triage_thresholds.${count}.${voter}`, label: `${voter}, ${count} options`, kind: "number", min: 0.01, max: 1,
    }))),
  },
  {
    id: "voters", title: "Voters", note: "Which voter may answer which kind of question.",
    fields: VOTERS.flatMap((voter) => KINDS.map((kind): Field => ({
      path: `classifier.triage_enabled.${voter}.${kind}`, label: `${voter}, ${kind}`, kind: "bool",
    }))),
  },
];

const view = ref<TuningView | null>(null);
const draft = ref<Record<string, number | boolean | null>>({});
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);

/** Reads `a.b.c` out of a nested object. */
function at(source: Record<string, unknown> | undefined, path: string): number | boolean | undefined {
  let node: unknown = source;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "number" || typeof node === "boolean" ? node : undefined;
}

const dirty = computed(() => Object.keys(draft.value).length > 0);
const isChanged = (path: string): boolean => path in (view.value?.overrides ?? {});
/** What the field shows: the draft when edited, else the value the agents use now. */
function shown(field: Field): number | boolean | "" {
  if (field.path in draft.value) return draft.value[field.path] ?? at(view.value?.defaults, field.path) ?? "";
  return at(view.value?.effective, field.path) ?? "";
}

function edit(field: Field, raw: string | boolean): void {
  saveError.value = "";
  const next = field.kind === "bool" ? raw === true : raw === "" ? NaN : Number(raw);
  const current = at(view.value?.effective, field.path);
  if (Number.isNaN(next) || next === current) delete draft.value[field.path];
  else draft.value[field.path] = next;
  draft.value = { ...draft.value };
}

/** Stage a return to the file's value; it applies on Save like any edit. */
function reset(field: Field): void {
  draft.value = { ...draft.value, [field.path]: null };
}

function cancel(): void {
  draft.value = {};
  saveError.value = "";
}

async function load(): Promise<void> {
  loadError.value = "";
  try {
    view.value = await tuningClient.get();
  } catch (error) {
    loadError.value = errorMessage(error);
  }
}

async function save(): Promise<void> {
  saving.value = true;
  saveError.value = "";
  try {
    view.value = await tuningClient.save(draft.value as TuningChanges);
    draft.value = {};
  } catch (error) {
    saveError.value = errorMessage(error);
  } finally {
    saving.value = false;
  }
}

const discardOpen = ref(false);
let discardAnswer: ((value: boolean) => void) | null = null;
function answerDiscard(discard: boolean): void {
  if (discard) cancel();
  discardOpen.value = false;
  discardAnswer?.(discard);
  discardAnswer = null;
}
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) onBeforeRouteLeave(() => {
  if (saving.value) return false;
  if (!dirty.value) return true;
  discardOpen.value = true;
  return new Promise<boolean>(resolve => { discardAnswer = resolve; });
});
function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = ""; }
}
onMounted(() => { void load(); window.addEventListener("beforeunload", beforeUnload); });
onUnmounted(() => { window.removeEventListener("beforeunload", beforeUnload); answerDiscard(false); });
</script>

<template>
  <PageLayout class="admin-panel" title="Tuning" description="Runtime limits and routing for the agents. Applies to every account; each agent picks a change up at the start of its next answer.">
    <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
    <template v-else-if="view">
      <section v-for="group in GROUPS" :key="group.id" class="card">
        <div class="section-head"><div><h3>{{ group.title }}</h3><p>{{ group.note }}</p></div></div>
        <SettingRow v-for="field in group.fields" :key="field.path" :setting-id="field.path" :label="field.label"
          :description="`File default: ${at(view.defaults, field.path) ?? 'Not set'}${field.unit ? ' ' + field.unit : ''}`"
          :data-row="field.path" :data-changed="isChanged(field.path)">
          <span v-if="isChanged(field.path) || field.path in draft" class="badge">Changed</span>
          <button v-if="isChanged(field.path) && draft[field.path] !== null" type="button" class="small" data-test="reset" :disabled="saving" :aria-label="`Reset ${field.label}`" @click="reset(field)">Reset</button>
          <ToggleSwitch v-if="field.kind === 'bool'" :id="field.path" :data-path="field.path" :aria-label="field.label" :checked="shown(field) === true" :disabled="saving"
            @change="edit(field, ($event.target as HTMLInputElement).checked)" />
          <input v-else :id="field.path" :data-path="field.path" :aria-label="field.label" type="number" :min="field.min" :max="field.max" :step="field.kind === 'int' ? 1 : 'any'" :value="shown(field)" :disabled="saving"
            @input="edit(field, ($event.target as HTMLInputElement).value)" />
          <span v-if="field.unit" class="muted">{{ field.unit }}</span>
        </SettingRow>
      </section>
      <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
      <div class="save-bar" role="group" aria-label="Tuning changes" :aria-busy="saving">
        <span v-if="dirty" class="dot" aria-hidden="true" />
        <span class="msg">{{ dirty ? 'Unsaved changes apply to every account.' : 'All changes saved.' }}</span>
        <button type="button" class="small" data-test="cancel" :disabled="!dirty || saving" @click="cancel">Cancel</button>
        <button type="button" class="primary" data-test="save" :disabled="!dirty || saving" :aria-busy="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>
    </template>
    <p v-else class="muted" role="status">Loading tuning…</p>
    <ConfirmModal v-if="discardOpen" :open="discardOpen" title="Discard unsaved tuning?" message="Your tuning changes have not been saved." confirm-label="Discard changes" @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
input[type="number"] { width: 10em; min-width: 0; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.save-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); }
.save-bar .msg { flex: 1 1 200px; font-size: 0.9em; }
.dot { width: 8px; height: 8px; border-radius: var(--radius-full); background: var(--accent); }
</style>
