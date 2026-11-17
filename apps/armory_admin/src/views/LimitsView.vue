<script setup lang="ts">
import { onMounted, ref } from "vue";
import { limitsClient, type CapabilityLimits, type LimitsCapability, type LimitsChanges, type LimitsView } from "../api/LimitsClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** How much one caller may use and how long files and links last, for the PDF and video capabilities. Saved in
 * Armory's database. Each capability reads these once when its engine starts, so a change is used from Armory's next start. */
interface Field { key: string; label: string; unit?: string; limit?: boolean }
interface Card { name: LimitsCapability; title: string; fields: Field[] }

const LIFETIMES: Field[] = [
  { key: "file_ttl_hours", label: "Keep a file for", unit: "hours" },
  { key: "sweep_interval_minutes", label: "Look for expired files every", unit: "minutes" },
  { key: "download_link_minutes", label: "A download link works for", unit: "minutes" },
];
const CARDS: Card[] = [
  {
    name: "pdf_merger", title: "PDF merging",
    fields: [
      ...LIFETIMES,
      { key: "mcp_wait_seconds", label: "Longest wait for a tool call (up to 100)", unit: "seconds" },
      { key: "max_file_mb", label: "Largest file", unit: "MB", limit: true },
      { key: "max_session_mb", label: "Most data per account", unit: "MB", limit: true },
      { key: "max_segments", label: "Most pieces in one merge", limit: true },
      { key: "max_output_pages", label: "Most pages in the result", limit: true },
      { key: "max_image_megapixels", label: "Largest image", unit: "megapixels", limit: true },
      { key: "max_concurrent_merges", label: "Merges at the same time", limit: true },
      { key: "job_timeout_seconds", label: "Longest merge", unit: "seconds", limit: true },
    ],
  },
  {
    name: "media_downloader", title: "Video downloads",
    fields: [
      ...LIFETIMES,
      { key: "max_file_mb", label: "Largest download", unit: "MB", limit: true },
      { key: "max_duration_minutes", label: "Longest video", unit: "minutes", limit: true },
      { key: "max_session_mb", label: "Most data per account", unit: "MB", limit: true },
      { key: "max_concurrent_downloads", label: "Downloads at the same time", limit: true },
      { key: "max_queued_downloads", label: "Downloads waiting in line", limit: true },
      { key: "max_caller_downloads", label: "Downloads per account at the same time", limit: true },
      { key: "job_timeout_minutes", label: "Longest download", unit: "minutes", limit: true },
    ],
  },
];

const view = ref<LimitsView | null>(null);
/** What was typed, by capability and field; a field absent here is unchanged. */
const edits = ref<Record<string, Record<string, string>>>({ pdf_merger: {}, media_downloader: {} });
const loading = ref(true);
const busy = ref("");
const error = ref("");
const notice = ref("");

function current(card: Card, field: Field): number {
  const document: CapabilityLimits = view.value![card.name];
  return field.limit ? document.limits[field.key] : (document[field.key as keyof CapabilityLimits] as number);
}

function shown(card: Card, field: Field): string {
  return edits.value[card.name][field.key] ?? String(current(card, field));
}

function type(card: Card, field: Field, value: string) {
  if (value.trim() === String(current(card, field))) delete edits.value[card.name][field.key];
  else edits.value[card.name][field.key] = value;
}

const changed = (card: Card) => Object.keys(edits.value[card.name]).length > 0;

function apply(next: LimitsView) {
  view.value = next;
  edits.value = { pdf_merger: {}, media_downloader: {} };
}

onMounted(async () => {
  try {
    apply(await limitsClient.get());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

async function save(card: Card) {
  const changes: LimitsChanges = {};
  const limits: Record<string, number> = {};
  for (const field of card.fields) {
    const text = edits.value[card.name][field.key];
    if (text === undefined) continue;
    const number = text.trim() === "" ? NaN : Number(text);
    if (field.limit) limits[field.key] = number;
    else changes[field.key] = number;
  }
  if (Object.keys(limits).length) changes.limits = limits;
  busy.value = card.name;
  error.value = notice.value = "";
  try {
    apply(await limitsClient.save(card.name, changes));
    notice.value = `${card.title}: saved. It is used from Armory's next start.`;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = "";
  }
}

async function reset(card: Card) {
  busy.value = card.name;
  error.value = notice.value = "";
  try {
    apply(await limitsClient.reset(card.name));
    notice.value = `${card.title}: back to the defaults. They are used from Armory's next start.`;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = "";
  }
}
</script>

<template>
  <PageLayout
    class="info-content limits"
    title="Limits"
    description="How much one account may use and how long files and links last, for PDF merging and video downloads. They are saved in Armory's database and used from Armory's next start."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="view" class="cards">
      <form v-for="card in CARDS" :key="card.name" class="card" :data-test="`card-${card.name}`" @submit.prevent="save(card)">
        <h2 class="title">{{ card.title }} <span v-if="view[card.name].stored" class="tag">changed</span></h2>
        <div v-for="field in card.fields" :key="field.key" class="field">
          <label :for="`${card.name}-${field.key}`">{{ field.label }}<span v-if="field.unit" class="unit"> ({{ field.unit }})</span></label>
          <input
            :id="`${card.name}-${field.key}`"
            :value="shown(card, field)"
            type="number"
            min="0"
            step="any"
            :disabled="busy !== ''"
            :data-test="field.key"
            @input="type(card, field, ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="actions">
          <button v-if="view[card.name].stored" type="button" class="chip" data-test="reset" :disabled="busy !== ''" @click="reset(card)">Use the defaults</button>
          <button type="submit" class="primary" data-test="save" :disabled="busy !== '' || !changed(card)">{{ busy === card.name ? "Saving…" : "Save" }}</button>
        </div>
      </form>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
  </PageLayout>
</template>

<style scoped>
.cards { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.tag { margin-left: 8px; padding: 1px 8px; border: 1px solid var(--accent); border-radius: var(--radius-full); font-size: 0.8em; font-weight: 400; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.unit { font-weight: 400; color: var(--muted); }
.field > input { min-width: 0; min-height: 44px; width: 100%; }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
</style>
