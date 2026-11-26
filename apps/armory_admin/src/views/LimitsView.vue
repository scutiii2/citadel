<script setup lang="ts">
import { FieldLabel } from "@citadel/ui";
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { limitsClient, type CapabilityLimits, type LimitsCapability, type LimitsChanges, type LimitsView } from "../api/LimitsClient";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import { errorMessage } from "../utils/errors";

/** How much one caller may use and how long files and links last, for stored files and the PDF and video capabilities. Saved in
 * Armory's database. Each capability reads these once when its engine starts, so a change is used from Armory's next start. */
interface Field { key: string; label: string; help: string; unit?: string; limit?: boolean }
interface Card { name: LimitsCapability; title: string; lede: string; fields: Field[] }

const LIFETIMES: Field[] = [
  { key: "file_ttl_hours", label: "Keep a file for", unit: "hours", help: "How long a stored file (an upload, a merged file or a finished download) is kept before it is removed." },
  { key: "sweep_interval_minutes", label: "Look for expired files every", unit: "minutes", help: "How often Armory looks for expired files and removes them." },
  { key: "download_link_minutes", label: "A download link works for", unit: "minutes", help: "How long a signed download link works after it is made." },
];
const CARDS: Card[] = [
  {
    name: "files", title: "Stored files", lede: "How long uploads and links last, and how much one account may store.",
    fields: [
      ...LIFETIMES,
      { key: "max_upload_mb", label: "Largest upload", unit: "MB", limit: true, help: "The size cap for one uploaded file that is not audio." },
      { key: "max_audio_upload_mb", label: "Largest audio upload", unit: "MB", limit: true, help: "The size cap for one uploaded audio file." },
      { key: "max_file_mb", label: "Largest stored file", unit: "MB", limit: true, help: "The size cap for any stored file, a merged PDF included." },
      { key: "max_session_mb", label: "Most data per account", unit: "MB", limit: true, help: "The size cap for all the files one account has stored." },
      { key: "max_image_megapixels", label: "Largest image", unit: "megapixels", limit: true, help: "The size cap for one uploaded image." },
    ],
  },
  {
    name: "pdf_merger", title: "PDF merging", lede: "How much one merge may use.",
    fields: [
      { key: "mcp_wait_seconds", label: "Longest wait for a tool call", unit: "seconds", help: "How long a tool call waits for a merge to finish before it answers \"still running\". At most 100." },
      { key: "max_segments", label: "Most pieces in one merge", limit: true, help: "The most pieces one merge may join." },
      { key: "max_output_pages", label: "Most pages in the result", limit: true, help: "The most pages the merged file may have." },
      { key: "max_concurrent_merges", label: "Merges at the same time", limit: true, help: "How many merges run at the same time. More wait for a free place." },
      { key: "job_timeout_seconds", label: "Longest merge", unit: "seconds", limit: true, help: "A merge that runs longer than this is stopped." },
    ],
  },
  {
    name: "media_downloader", title: "Video downloads", lede: "How long files and links last, and how much one account and one download may use.",
    fields: [
      ...LIFETIMES,
      { key: "max_file_mb", label: "Largest download", unit: "MB", limit: true, help: "The size cap for one download." },
      { key: "max_duration_minutes", label: "Longest video", unit: "minutes", limit: true, help: "The length cap for one video." },
      { key: "max_session_mb", label: "Most data per account", unit: "MB", limit: true, help: "The size cap for all the files one account has stored." },
      { key: "max_concurrent_downloads", label: "Downloads at the same time", limit: true, help: "How many downloads run at the same time." },
      { key: "max_queued_downloads", label: "Downloads waiting in line", limit: true, help: "How many downloads may wait for a free place." },
      { key: "max_caller_downloads", label: "Downloads per account at the same time", limit: true, help: "How many downloads one account may have going at the same time." },
      { key: "job_timeout_minutes", label: "Longest download", unit: "minutes", limit: true, help: "A download that runs longer than this is stopped." },
    ],
  },
];

const noEdits = (): Record<string, Record<string, string>> => ({ files: {}, pdf_merger: {}, media_downloader: {} });

const view = ref<LimitsView | null>(null);
/** What was typed, by capability and field; a field absent here is unchanged. */
const edits = ref(noEdits());
const loading = ref(true);
const busy = ref("");
const error = ref("");
const notice = ref("");
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();

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
const dirty = computed(() => CARDS.some(changed));

function apply(next: LimitsView) {
  view.value = next;
  edits.value = noEdits();
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

/** Saves each capability that has edits, one request each; a refusal stops there and keeps the rest of the draft. */
async function save() {
  if (!dirty.value || busy.value) return;
  busy.value = "all";
  error.value = notice.value = "";
  await panel.value?.keepFocus(async () => {
    const saved: string[] = [];
    try {
      for (const card of CARDS.filter(changed)) {
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
        const next = await limitsClient.save(card.name, changes);
        view.value = next;
        edits.value = { ...edits.value, [card.name]: {} };
        saved.push(card.title);
      }
      notice.value = `${saved.join(" and ")}: saved. It is used from Armory's next start.`;
    } catch (err) {
      error.value = errorMessage(err);
    } finally {
      busy.value = "";
    }
  });
}

function discard() {
  edits.value = noEdits();
  error.value = notice.value = "";
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
  <SettingsPanel ref="panel" v-model:search="search" title="Limits" heading="Capability limits" label="limits" :dirty="dirty" :saving="busy !== ''" @save="save" @discard="discard">
    <template #help>
      <p>How much one account may use and how long files and links last, for stored files, PDF merging and video downloads.</p>
      <p>They are saved in Armory's database and used from Armory's next start.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading…</p>
    <div v-else-if="view" class="cards">
      <ActionMessage v-if="error" kind="error" :text="error" class="note" />
      <p v-if="notice" class="note muted" role="status" data-test="notice">{{ notice }}</p>
      <section v-for="card in CARDS" v-show="panel?.matches(card.title, ...card.fields.map((field) => field.label))" :key="card.name" class="group fields" :data-test="`card-${card.name}`" :aria-labelledby="`${card.name}-title`">
        <h3 :id="`${card.name}-title`">{{ card.title }} <span v-if="view[card.name].stored" class="tag">changed</span></h3>
        <p class="lede">{{ card.lede }}</p>
        <div v-for="field in card.fields" v-show="panel?.matches(card.title, field.label)" :key="field.key" class="field">
          <FieldLabel :title="field.unit ? `${field.label} (${field.unit})` : field.label" :for="`${card.name}-${field.key}`">{{ field.help }}</FieldLabel>
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
        <div v-if="view[card.name].stored" class="actions">
          <button type="button" class="chip" data-test="reset" :disabled="busy !== ''" @click="reset(card)">Use the defaults</button>
        </div>
      </section>
    </div>
    <ActionMessage v-else-if="error" kind="error" :text="error" class="note" />
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.error { color: var(--danger); }
.muted { color: var(--muted); }
.cards { display: grid; }
.group { display: grid; gap: 12px; max-width: 720px; padding: 16px; }
.group + .group { border-top: 1px solid var(--border); }
.group h3 { margin: 0; font-size: 1em; }
.tag { margin-left: 8px; padding: 1px 8px; border: 1px solid var(--accent); border-radius: var(--radius-full); font-size: 0.8em; font-weight: 400; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.unit { font-weight: 400; color: var(--muted); }
.field > input { min-width: 0; min-height: 44px; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.actions { display: flex; }
.group.fields { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); max-width: none; align-items: start; }
.group.fields > h3, .group.fields > .lede { grid-column: 1 / -1; }
.lede { margin: -8px 0 0; color: var(--muted); font-size: 0.9em; }
</style>
