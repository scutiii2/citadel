<script setup lang="ts">
import FieldLabel from "../components/admin/FieldLabel.vue";
import ActionMessage from "../components/admin/ActionMessage.vue";
import { computed, onMounted, ref } from "vue";
import { ticketSettingsClient } from "../api/TicketSettingsClient";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import { errorMessage } from "../utils/errors";

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
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();
const baseline = ref("");

const snapshot = () => JSON.stringify([tags.value.map((row) => [row.name, row.description]), autoHourlyCap.value, recentHours.value, minConfidence.value, candidates.value, timeoutSeconds.value]);
const dirty = computed(() => !loading.value && snapshot() !== baseline.value);

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
  baseline.value = snapshot();
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
  if (!dirty.value || saving.value) return;
  error.value = notice.value = "";
  if (problem.value) { error.value = problem.value; return; }
  saving.value = true;
  await panel.value?.keepFocus(async () => {
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
  });
}

function discard() {
  const saved = JSON.parse(baseline.value) as [string[][], number, number, number, number, number];
  tags.value = saved[0].map(([name, description]) => ({ key: nextKey++, name, description }));
  [autoHourlyCap.value, recentHours.value, minConfidence.value, candidates.value, timeoutSeconds.value] = saved.slice(1) as [number, number, number, number, number];
  error.value = notice.value = "";
}
</script>

<template>
  <SettingsPanel ref="panel" v-model:search="search" title="Ticket settings" heading="Ticket rules" label="ticket settings" :dirty="dirty" :saving="saving" @save="save" @discard="discard">
    <template #help>
      <p>The tags tickets can get and the limits for tickets Laya files. Saved in Armory's database, and the next ticket uses a saved change.</p>
      <p>Laya picks from the tags when it sorts a ticket, so write each description as a plain rule. Keep {{ MIN_TAGS }} to {{ MAX_TAGS }} tags. The elevation rules are not edited here.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <ActionMessage v-if="error" kind="error" :text="error" class="note" />
      <p v-if="notice" class="note muted" role="status" data-test="notice">{{ notice }}</p>
      <p v-if="problem && dirty" class="note muted" data-test="problem">{{ problem }}</p>
      <section v-show="panel?.matches('Tags', ...tags.map((row) => row.name + ' ' + row.description))" class="group" aria-labelledby="tags-title">
        <h3 id="tags-title">Tags</h3>
        <div v-for="row in tags" :key="row.key" class="tag" data-test="tag">
          <input v-model="row.name" aria-label="Tag name" class="name" autocomplete="off" spellcheck="false" :disabled="saving" data-test="tag-name" />
          <input v-model="row.description" aria-label="Tag description" class="desc" autocomplete="off" :disabled="saving" data-test="tag-description" />
          <button type="button" class="admin-icon" title="Remove tag" aria-label="Remove tag" :disabled="saving || tags.length <= MIN_TAGS" data-test="tag-remove" @click="removeTag(row.key)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13" /></svg>
          </button>
        </div>
        <div>
          <button type="button" class="admin-icon" title="Add tag" aria-label="Add tag" :disabled="saving || tags.length >= MAX_TAGS" data-test="tag-add" @click="addTag">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>
      </section>

      <section v-show="panel?.matches('Limits', 'Tickets Laya may file per hour', 'Hours a ticket counts as recent')" class="group fields" aria-labelledby="limits-title">
        <h3 id="limits-title">Limits</h3>
        <p class="lede">How many tickets Laya may file by itself, and how long a ticket counts as recent.</p>
        <div class="field">
          <FieldLabel title="Tickets Laya may file per hour" for="cap">The most tickets Laya may file on its own in one hour. Past it, Laya stops filing until the limit allows more. Whole number, at least 1.</FieldLabel>
          <input id="cap" v-model.number="autoHourlyCap" type="number" min="1" step="1" :disabled="saving" data-test="cap" />
        </div>
        <div class="field">
          <FieldLabel title="Hours a ticket counts as recent" for="recent">How many hours back a ticket still counts as recent. Whole number, at least 1.</FieldLabel>
          <input id="recent" v-model.number="recentHours" type="number" min="1" step="1" :disabled="saving" data-test="recent" />
        </div>
      </section>

      <section v-show="panel?.matches('Laya', 'Least confidence to act', 'Similar tickets to compare', 'Seconds to wait for Laya')" class="group fields" aria-labelledby="laya-title">
        <h3 id="laya-title">Laya</h3>
        <p class="lede">How Laya compares a new ticket with the tickets already filed.</p>
        <div class="field">
          <FieldLabel title="Least confidence to act (0 to 1)" for="confidence">How sure Laya must be before it acts on a ticket. Above 0 and at most 1.</FieldLabel>
          <input id="confidence" v-model.number="minConfidence" type="number" min="0.01" max="1" step="0.01" :disabled="saving" data-test="confidence" />
        </div>
        <div class="field">
          <FieldLabel title="Similar tickets to compare (1 to 10)" for="candidates">How many existing tickets Laya compares a new ticket with. Whole number, 1 to 10.</FieldLabel>
          <input id="candidates" v-model.number="candidates" type="number" min="1" max="10" step="1" :disabled="saving" data-test="candidates" />
        </div>
        <div class="field">
          <FieldLabel title="Seconds to wait for Laya" for="timeout">How long to wait for Laya's answer. Above 0.</FieldLabel>
          <input id="timeout" v-model.number="timeoutSeconds" type="number" min="1" step="1" :disabled="saving" data-test="timeout" />
        </div>
      </section>
    </form>
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.error { color: var(--danger); }
.muted { color: var(--muted); }
.form { display: grid; }
.group { display: grid; gap: 12px; max-width: 720px; padding: 16px; }
.group + .group { border-top: 1px solid var(--border); }
.group h3 { margin: 0; font-size: 1em; }
.tag { display: grid; grid-template-columns: minmax(80px, 160px) minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.field { display: grid; gap: 4px; }
.field > label { font-size: 0.9em; font-weight: 600; }
.tag input, .field input { min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
@media (max-width: 560px) {
  .tag { grid-template-columns: minmax(0, 1fr) auto; }
  .tag .desc { grid-column: 1 / -1; grid-row: 2; }
}
.group.fields { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); max-width: none; align-items: start; }
.group.fields > h3, .group.fields > .lede { grid-column: 1 / -1; }
.lede { margin: -8px 0 0; color: var(--muted); font-size: 0.9em; }
</style>
