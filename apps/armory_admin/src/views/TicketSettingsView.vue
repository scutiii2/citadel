<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ticketSettingsClient } from "../api/TicketSettingsClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** The ticket settings Armory keeps in its database: the tags tickets get, how often Laya may file,
 * and Laya's limits. A saved change is used by the next ticket. The elevation rules are not edited here. */
const MIN_TAGS = 2;
const MAX_TAGS = 10;

interface TagRow { key: number; name: string; description: string }

let nextKey = 0;
const tags = ref<TagRow[]>([]);
const autoHourlyCap = ref(5);
const recentHours = ref(24);
const minConfidence = ref(0.7);
const candidates = ref(5);
const timeoutSeconds = ref(20);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const names = computed(() => tags.value.map((row) => row.name.trim().toLowerCase()));
const problem = computed(() => {
  if (tags.value.length < MIN_TAGS) return `Keep at least ${MIN_TAGS} tags.`;
  if (tags.value.some((row) => !row.name.trim() || !row.description.trim())) return "Every tag needs a name and a description.";
  if (new Set(names.value).size !== names.value.length) return "Tag names must be different.";
  if (!(minConfidence.value > 0 && minConfidence.value <= 1)) return "Laya confidence must be above 0 and at most 1.";
  return "";
});

function apply(document: Awaited<ReturnType<typeof ticketSettingsClient.get>>) {
  tags.value = Object.entries(document.tags).map(([name, description]) => ({ key: nextKey++, name, description }));
  autoHourlyCap.value = document.auto_hourly_cap;
  recentHours.value = document.recent_hours;
  minConfidence.value = document.laya.min_confidence;
  candidates.value = document.laya.candidates;
  timeoutSeconds.value = document.laya.timeout_seconds;
}

onMounted(async () => {
  try {
    apply(await ticketSettingsClient.get());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

function addTag() {
  if (tags.value.length < MAX_TAGS) tags.value.push({ key: nextKey++, name: "", description: "" });
}

function removeTag(key: number) {
  tags.value = tags.value.filter((row) => row.key !== key);
}

async function save() {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(
      await ticketSettingsClient.save({
        tags: Object.fromEntries(tags.value.map((row) => [row.name.trim().toLowerCase(), row.description.trim()])),
        auto_hourly_cap: autoHourlyCap.value,
        recent_hours: recentHours.value,
        laya: { min_confidence: minConfidence.value, candidates: candidates.value, timeout_seconds: timeoutSeconds.value },
      }),
    );
    notice.value = "Saved. The next ticket uses it.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageLayout
    class="info-content ticket-settings"
    title="Ticket settings"
    description="The tags tickets can get and the limits for tickets Laya files. Saved in Armory's database."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <section class="card" aria-labelledby="tags-title">
        <h2 id="tags-title" class="title">Tags</h2>
        <p class="help">Laya picks from these when it sorts a ticket, so write each description as a plain rule. {{ MIN_TAGS }} to {{ MAX_TAGS }} tags.</p>
        <div v-for="row in tags" :key="row.key" class="tag" data-test="tag">
          <input v-model="row.name" aria-label="Tag name" class="name" autocomplete="off" spellcheck="false" :disabled="saving" data-test="tag-name" />
          <input v-model="row.description" aria-label="Tag description" class="desc" autocomplete="off" :disabled="saving" data-test="tag-description" />
          <button type="button" class="chip" :disabled="saving || tags.length <= MIN_TAGS" data-test="tag-remove" @click="removeTag(row.key)">Remove</button>
        </div>
        <div>
          <button type="button" class="chip" :disabled="saving || tags.length >= MAX_TAGS" data-test="tag-add" @click="addTag">Add tag</button>
        </div>
      </section>

      <section class="card" aria-labelledby="limits-title">
        <h2 id="limits-title" class="title">Limits</h2>
        <div class="field">
          <label for="cap">Tickets Laya may file per hour</label>
          <input id="cap" v-model.number="autoHourlyCap" type="number" min="1" step="1" :disabled="saving" data-test="cap" />
        </div>
        <div class="field">
          <label for="recent">Hours a ticket counts as recent</label>
          <input id="recent" v-model.number="recentHours" type="number" min="1" step="1" :disabled="saving" data-test="recent" />
        </div>
      </section>

      <section class="card" aria-labelledby="laya-title">
        <h2 id="laya-title" class="title">Laya</h2>
        <div class="field">
          <label for="confidence">Least confidence to act (0 to 1)</label>
          <input id="confidence" v-model.number="minConfidence" type="number" min="0.01" max="1" step="0.01" :disabled="saving" data-test="confidence" />
        </div>
        <div class="field">
          <label for="candidates">Similar tickets to compare (1 to 10)</label>
          <input id="candidates" v-model.number="candidates" type="number" min="1" max="10" step="1" :disabled="saving" data-test="candidates" />
        </div>
        <div class="field">
          <label for="timeout">Seconds to wait for Laya</label>
          <input id="timeout" v-model.number="timeoutSeconds" type="number" min="1" step="1" :disabled="saving" data-test="timeout" />
        </div>
      </section>

      <p v-if="problem" class="help" data-test="problem">{{ problem }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="saving || !!problem">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </PageLayout>
</template>

<style scoped>
.form { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.tag { display: grid; grid-template-columns: minmax(80px, 160px) minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.field { display: grid; gap: 4px; }
.field > label { font-size: 0.9em; font-weight: 600; }
.tag input, .field input { min-width: 0; min-height: 44px; }
.actions { display: flex; justify-content: flex-end; }
@media (max-width: 560px) {
  .tag { grid-template-columns: minmax(0, 1fr); }
}
</style>
