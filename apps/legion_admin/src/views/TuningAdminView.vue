<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import SettingRow from "../components/SettingRow.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import PageLayout from "../components/PageLayout.vue";
import { tuningClient, type TuningChanges, type TuningView } from "../api/TuningClient";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** One editable value: where it lives in config_tuning.json, how to label it, and its bounds
 * (the same ones legion enforces; legion's answer is what the page shows on a refusal). */
interface Field {
  path: string;
  label: string;
  kind: "int" | "number" | "bool" | "enum";
  options?: string[];
  unit?: string;
  min?: number;
  max?: number;
}
interface Group { id: string; title: string; note: string; fields: Field[] }

const STRATEGIES = ["laya-only", "jev-only", "both"];

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
    id: "classifier", title: "Classifier", note: "Timeout and input limits for automatic routing and tier decisions.",
    fields: [
      { path: "classifier.timeout_seconds", label: "Timeout", kind: "number", unit: "s", min: 0.1, max: 60 },
      { path: "classifier.max_input_chars", label: "Max input characters", kind: "int", min: 1, max: 1000000 },
    ],
  },
  ...(["auto_tier", "auto_route"] as const).map((feature): Group => ({
    id: feature, title: feature === "auto_tier" ? "Automatic model tier" : "Automatic specialist routing",
    note: "Gateway strategy and confidence for this feature. Enable the feature in its configuration file.",
    fields: [
      { path: `classifier.${feature}.strategy`, label: "Decision strategy", kind: "enum", options: STRATEGIES },
      { path: `classifier.${feature}.min_confidence`, label: "Minimum confidence", kind: "int", min: 0, max: 100, unit: "%" },
    ],
  })),
];

const view = ref<TuningView | null>(null);
const draft = ref<Record<string, number | boolean | string | null>>({});
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const invalidPath = ref("");
const visibleGroups = computed(() => {
  const query = search.value.trim().toLowerCase();
  return GROUPS.map((group) => ({
    ...group,
    fields: group.fields.filter((field) => [group.title, group.note, field.label, field.path].some((text) => text.toLowerCase().includes(query))),
  })).filter((group) => group.fields.length);
});

/** Reads `a.b.c` out of a nested object. */
function at(source: Record<string, unknown> | undefined, path: string): number | boolean | string | undefined {
  let node: unknown = source;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "number" || typeof node === "boolean" || typeof node === "string" ? node : undefined;
}

const dirty = computed(() => Object.keys(draft.value).length > 0);
watch(dirty, (value) => {
  const active = document.activeElement as HTMLElement | null;
  if (!value && active?.closest(".tuning-actions")) void nextTick(() => searchField.value?.focus());
});
const isChanged = (path: string): boolean => path in (view.value?.overrides ?? {});
/** What the field shows: the draft when edited, else the value the agents use now. */
function shown(field: Field): number | boolean | string {
  if (field.path in draft.value) return draft.value[field.path] ?? at(view.value?.defaults, field.path) ?? "";
  return at(view.value?.effective, field.path) ?? "";
}

function edit(field: Field, raw: string | boolean): void {
  saveError.value = "";
  invalidPath.value = "";
  const next = field.kind === "enum" ? String(raw) : field.kind === "bool" ? raw === true : raw === "" ? raw : Number(raw);
  const current = at(view.value?.effective, field.path);
  if (next === current) delete draft.value[field.path];
  else draft.value[field.path] = next;
  draft.value = { ...draft.value };
}

/** Stage a return to the file's value; it applies on Save like any edit. */
function reset(field: Field): void {
  invalidPath.value = saveError.value = "";
  draft.value = { ...draft.value, [field.path]: null };
}

function cancel(): void {
  draft.value = {};
  invalidPath.value = saveError.value = "";
}

function isValid(field: Field, value: number | string | boolean | null | undefined): boolean {
  if (value == null) return true;
  if (field.kind === "enum") return typeof value === "string" && !!field.options?.includes(value);
  if (field.kind === "bool") return typeof value === "boolean";
  return typeof value === "number" && Number.isFinite(value) && value >= (field.min ?? -Infinity) &&
    value <= (field.max ?? Infinity) && (field.kind !== "int" || Number.isInteger(value));
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
  if (!dirty.value || saving.value) return;
  invalidPath.value = saveError.value = "";
  const invalid = GROUPS.flatMap((group) => group.fields).find((field) => !isValid(field, draft.value[field.path]));
  if (invalid) {
    invalidPath.value = invalid.path;
    saveError.value = invalid.min === undefined ? `Enter a valid value for ${invalid.label}.` :
      `Enter ${invalid.kind === "int" ? "a whole number" : "a number"} from ${invalid.min} to ${invalid.max} for ${invalid.label}.`;
    if (!visibleGroups.value.some((group) => group.fields.includes(invalid))) search.value = "";
    await nextTick();
    document.getElementById(invalid.path)?.focus();
    return;
  }
  const saveHadFocus = !!document.activeElement?.closest(".tuning-actions");
  saving.value = true;
  try {
    view.value = await tuningClient.save(draft.value as TuningChanges);
    cancel();
    await nextTick();
    if (saveHadFocus && document.activeElement === document.body) searchField.value?.focus();
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
  if (!discardAnswer && discard) {
    void nextTick(async () => {
      await nextTick();
      searchField.value?.focus();
    });
  }
  discardOpen.value = false;
  discardAnswer?.(discard);
  discardAnswer = null;
}
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) onBeforeRouteLeave(() => {
  if (saving.value) return false;
  if (!dirty.value) return true;
  discardOpen.value = true;
  discardAnswer?.(false);
  return new Promise<boolean>(resolve => { discardAnswer = resolve; });
});
function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = ""; }
}
onMounted(() => { void load(); window.addEventListener("beforeunload", beforeUnload); });
onUnmounted(() => { window.removeEventListener("beforeunload", beforeUnload); answerDiscard(false); });
</script>

<template>
  <PageLayout class="admin-panel" title="Tuning" wide>
    <section class="admin-panel-card" aria-labelledby="tuning-title">
      <header class="admin-panel-head">
        <h2 id="tuning-title">Runtime settings</h2>
        <div class="admin-panel-tools tuning-tools">
          <div class="tuning-actions" aria-label="Tuning changes" role="group">
            <button v-if="dirty" type="button" class="small" data-test="cancel" :disabled="saving" @click="discardOpen = true">Cancel</button>
            <button v-if="dirty" type="button" class="admin-icon save-icon" data-test="save" title="Save tuning changes" aria-label="Save tuning changes"
              :disabled="saving" :aria-busy="saving" @click="save">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 3h13l4 4v14H3V3h1zm3 0v6h10V3M7 21v-8h10v8" /></svg>
            </button>
          </div>
          <AdminSearch ref="searchField" v-model="search" label="Search settings" />
        </div>
      </header>
      <p v-if="loadError" class="admin-panel-text error" role="alert">{{ loadError }} <button type="button" class="small" @click="load">Retry</button></p>
      <p v-else-if="!view" class="admin-panel-text muted" role="status">Loading tuning…</p>
      <template v-else>
        <p v-if="!visibleGroups.length" class="admin-panel-text muted">No settings match your search. <button type="button" class="small" @click="search = ''; searchField?.focus()">Clear search</button></p>
        <p v-if="saveError && !invalidPath" class="admin-panel-text error" role="alert">{{ saveError }}</p>
        <section v-for="group in visibleGroups" :key="group.id" class="tuning-group">
          <div class="section-head"><div><h3>{{ group.title }}</h3><p>{{ group.note }}</p></div></div>
        <SettingRow v-for="field in group.fields" :key="field.path" :setting-id="field.path" :label="field.label"
          :description="`File default: ${at(view.defaults, field.path) ?? 'Not set'}${field.unit ? ' ' + field.unit : ''}`"
          :data-row="field.path" :data-changed="isChanged(field.path)">
          <span v-if="isChanged(field.path) || field.path in draft" class="badge">Changed</span>
          <button v-if="isChanged(field.path) && draft[field.path] !== null" type="button" class="small" data-test="reset" :disabled="saving" :aria-label="`Reset ${field.label}`" @click="reset(field)">Reset</button>
          <ToggleSwitch v-if="field.kind === 'bool'" :id="field.path" :data-path="field.path" :aria-label="field.label" :checked="shown(field) === true" :disabled="saving"
            @change="edit(field, ($event.target as HTMLInputElement).checked)" />
          <select v-else-if="field.kind === 'enum'" :id="field.path" :data-path="field.path" :aria-label="field.label" :value="shown(field)" :disabled="saving"
            @change="edit(field, ($event.target as HTMLSelectElement).value)"><option v-for="option in field.options" :key="option" :value="option">{{ option }}</option></select>
          <input v-else :id="field.path" :data-path="field.path" :aria-label="field.label" type="number" :aria-invalid="invalidPath === field.path || undefined" :aria-describedby="invalidPath === field.path ? `${field.path}-error` : undefined" :min="field.min" :max="field.max" :step="field.kind === 'int' ? 1 : 'any'" :value="shown(field)" :disabled="saving"
            @input="edit(field, ($event.target as HTMLInputElement).value)" />
          <span v-if="field.unit" class="muted">{{ field.unit }}</span>
          <span v-if="invalidPath === field.path" :id="`${field.path}-error`" class="error" role="alert">{{ saveError }}</span>
        </SettingRow>
        </section>
      </template>
    </section>
    <ConfirmModal v-if="discardOpen" :open="discardOpen" title="Discard unsaved tuning?" message="Your tuning changes have not been saved." confirm-label="Discard changes" @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
input[type="number"], select { width: 10em; min-width: 0; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.tuning-group { padding: 14px 16px; }
.tuning-group + .tuning-group { border-top: 1px solid var(--border); }
.tuning-tools { display: grid; grid-template-columns: 112px minmax(0, 240px); gap: 6px; }
.tuning-tools :deep(.search) { min-width: 0; }
.tuning-actions { display: flex; justify-content: flex-end; align-items: center; gap: 4px; }
.save-icon { color: var(--accent); }
@media (max-width: 767px) {
  .tuning-actions .small { min-height: 44px; }
  .tuning-tools { width: min(100%, 358px); grid-template-columns: 112px minmax(0, 1fr); }
}
</style>
