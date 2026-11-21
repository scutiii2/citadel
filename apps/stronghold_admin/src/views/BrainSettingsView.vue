<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { brainSettingsClient, type BrainSettings, type BrainSettingsChanges, type Part } from "../api/BrainSettingsClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** The Brain's run-time limits. Stronghold owns them: it checks every value against its own ranges (sent in the
 * answer, used here for the input limits), saves them in its settings database and uses a change at once. */
interface FieldSpec { key: string; label: string; help?: string; step?: string }
interface PartSpec { part: Part; title: string; intro: string; fields: FieldSpec[] }

const NOTICE = "Saving lower limits leaves existing data in place. The next new short-term item can remove older unpinned items to make room. Lower file and sharing limits can block new files, edits that increase storage use, or new shares.";

const PARTS: PartSpec[] = [
  {
    part: "stack", title: "Short-term memory", intro: "The short facts kept for one chat.",
    fields: [
      { key: "max_items", label: "Items per chat", help: "Adding an item removes the oldest unpinned items as needed. If there are too many pinned items to make room, the add is refused." },
      { key: "max_item_chars", label: "Characters per item" },
      { key: "compact_item_chars", label: "Characters per summary item", help: "The longest summary compaction may write." },
      { key: "warn_ratio", label: "Warn at this fraction of capacity", step: "any" },
    ],
  },
  {
    part: "long_term", title: "Long-term memory", intro: "The Markdown files kept for one account.",
    fields: [
      { key: "max_record_chars", label: "Characters per file body" },
      { key: "max_files", label: "Files per account" },
      { key: "max_total_bytes", label: "Bytes per account", help: "Counts the saved original text of edited files too." },
      { key: "search_limit", label: "Search results by default" },
    ],
  },
  {
    part: "sharing", title: "Sharing", intro: "Copies sent between accounts and to the global brain.",
    fields: [
      { key: "max_share_chars", label: "Characters per shared body" },
      { key: "max_pending_sent", label: "Waiting shares per sender" },
      { key: "max_inbox", label: "Waiting shares per account" },
      { key: "max_global_queue", label: "Shares waiting for review in the global brain" },
    ],
  },
];

const saved = ref<BrainSettings | null>(null);
const values = ref<Record<string, string>>({});
const loading = ref(true);
const saving = ref(false);
const loadError = ref("");
const error = ref("");
const notice = ref("");

const id = (part: Part, key: string) => `${part}.${key}`;
const parts = computed(() => PARTS.filter((spec) => saved.value?.[spec.part]));
const savedValue = (part: Part, key: string): number | undefined => (saved.value?.[part] as Record<string, number> | undefined)?.[key];
const rangeOf = (part: Part, key: string) => saved.value?.ranges[part]?.[key];

function apply(view: BrainSettings): void {
  saved.value = view;
  const next: Record<string, string> = {};
  for (const spec of PARTS) {
    for (const field of spec.fields) {
      const value = (view[spec.part] as Record<string, number> | undefined)?.[field.key];
      if (value !== undefined) next[id(spec.part, field.key)] = String(value);
    }
  }
  values.value = next;
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    apply(await brainSettingsClient.get());
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function problemOf(part: Part, key: string): string {
  const text = (values.value[id(part, key)] ?? "").trim();
  const number = Number(text);
  if (text === "" || !Number.isFinite(number)) return "Enter a number.";
  if (key !== "warn_ratio" && !Number.isInteger(number)) return "Use a whole number.";
  const range = rangeOf(part, key);
  if (range && (number < range[0] || number > range[1])) return `From ${range[0]} to ${range[1]}.`;
  return "";
}

function changedField(part: Part, key: string): boolean {
  const text = (values.value[id(part, key)] ?? "").trim();
  const before = savedValue(part, key);
  return text !== String(before) && Number(text) !== before;
}

const changes = computed<BrainSettingsChanges>(() => {
  const found: Record<string, Record<string, number>> = {};
  for (const spec of parts.value) {
    for (const field of spec.fields) {
      if (changedField(spec.part, field.key)) (found[spec.part] ??= {})[field.key] = Number(values.value[id(spec.part, field.key)]);
    }
  }
  return found as BrainSettingsChanges;
});
const anyProblem = computed(() => parts.value.some((spec) => spec.fields.some((field) => problemOf(spec.part, field.key) !== "")));
const canSave = computed(() => Object.keys(changes.value).length > 0 && !anyProblem.value && !saving.value);

function formatBytes(bytes: number): string {
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
}
const bytesHint = (part: Part, key: string): string => {
  const text = (values.value[id(part, key)] ?? "").trim();
  return key === "max_total_bytes" && text !== "" && problemOf(part, key) === "" ? `About ${formatBytes(Number(text))}.` : "";
};

async function save(): Promise<void> {
  if (!canSave.value) return;
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await brainSettingsClient.save(changes.value));
    notice.value = "Saved. Stronghold uses it now.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageLayout
    class="info-content brain-settings"
    title="Brain settings"
    description="Manage how much short-term memory, long-term memory and sharing Stronghold allows."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="loadError" class="load-error" role="alert">
      <p class="error">{{ loadError }}</p>
      <button type="button" class="chip" data-test="retry" @click="load">Try again</button>
    </div>
    <form v-else-if="saved" class="form" data-test="form" novalidate @submit.prevent="save">
      <section class="card" aria-labelledby="root-title">
        <h2 id="root-title" class="title">Where the files are kept</h2>
        <p class="path" data-test="root">{{ saved.root }}</p>
        <p class="help">Set by STRONGHOLD_BRAIN_ROOT or the brain/root setting. Moving the folder requires copying its contents and restarting Stronghold.</p>
      </section>

      <section v-for="spec in parts" :key="spec.part" class="card" :aria-labelledby="`${spec.part}-title`">
        <h2 :id="`${spec.part}-title`" class="title">{{ spec.title }}</h2>
        <p class="help">{{ spec.intro }}</p>
        <p class="help" :data-test="`state-${spec.part}`">{{ saved.stored[spec.part] ? "Stronghold marks this part as changed from the defaults." : "Using the defaults." }}</p>
        <div v-for="field in spec.fields" :key="field.key" class="field">
          <label :for="`f-${id(spec.part, field.key)}`">{{ field.label }}</label>
          <input
            :id="`f-${id(spec.part, field.key)}`" :value="values[id(spec.part, field.key)]" type="number"
            @input="values[id(spec.part, field.key)] = ($event.target as HTMLInputElement).value"
            :min="rangeOf(spec.part, field.key)?.[0]" :max="rangeOf(spec.part, field.key)?.[1]" :step="field.step ?? '1'"
            :disabled="saving" :data-test="id(spec.part, field.key)"
            :aria-invalid="problemOf(spec.part, field.key) ? 'true' : undefined"
            :aria-describedby="problemOf(spec.part, field.key) ? `problem-${id(spec.part, field.key)}` : undefined"
          />
          <p v-if="problemOf(spec.part, field.key)" :id="`problem-${id(spec.part, field.key)}`" class="problem" :data-test="`problem-${id(spec.part, field.key)}`">{{ problemOf(spec.part, field.key) }}</p>
          <p v-if="field.help" class="help">{{ field.help }}</p>
          <p v-if="bytesHint(spec.part, field.key)" class="help" :data-test="`hint-${id(spec.part, field.key)}`">{{ bytesHint(spec.part, field.key) }}</p>
        </div>
      </section>

      <p class="help">{{ NOTICE }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="!canSave" :aria-busy="saving">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </PageLayout>
</template>

<style scoped>
.form { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input { min-width: 0; min-height: 44px; width: 100%; }
.help, .path, .problem { margin: 0; font-size: 0.85em; }
.help { color: var(--muted); }
.path { font-family: var(--mono); overflow-wrap: anywhere; }
.problem { color: var(--text); font-weight: 600; }
.load-error { display: grid; gap: 8px; justify-items: start; }
.actions { display: flex; justify-content: flex-end; }
.actions > button, .load-error > button { min-height: 44px; }
</style>
