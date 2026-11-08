<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { settingsClient } from "../../api/SettingsClient";
import { EMBER_WEB_PAGES } from "../../utils/emberWebPages";
import { errorMessage } from "../../utils/errors";
import ToggleSwitch from "../ToggleSwitch.vue";
import "./admin.css";

/** Which ember_web pages every account's sidebar shows. Hiding is nav only: a hidden page
 * still opens by its address. Like the other setting that reaches every account, a flip is a
 * draft until Save. */
const known = new Set<string>(EMBER_WEB_PAGES.map((page) => page.id));

const stored = ref<string[] | null>(null);
// The pages the draft hides, among the ones listed here.
const draft = ref<Set<string>>(new Set());
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);

/** Ids ember_web may know but this page does not list: kept as they are on every save. */
const unknownHidden = computed(() => (stored.value ?? []).filter((id) => !known.has(id)));
const storedKnown = computed(() => new Set((stored.value ?? []).filter((id) => known.has(id))));
const dirty = computed(
  () => stored.value !== null && (draft.value.size !== storedKnown.value.size || [...draft.value].some((id) => !storedKnown.value.has(id))),
);
const anyHidden = computed(() => draft.value.size > 0 || unknownHidden.value.length > 0);

function useStored(list: string[]): void {
  stored.value = list;
  draft.value = new Set(list.filter((id) => known.has(id)));
}

async function load(): Promise<void> {
  loadError.value = "";
  try {
    useStored((await settingsClient.pages()).hidden);
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

function setShown(id: string, shown: boolean): void {
  const next = new Set(draft.value);
  if (shown) next.delete(id);
  else next.add(id);
  draft.value = next;
  saved.value = false;
  saveError.value = "";
}

/** Shows every page again. Like any flip it is a draft until Save. */
function resetToDefault(): void {
  draft.value = new Set();
  saved.value = false;
  saveError.value = "";
}

function cancel(): void {
  draft.value = new Set(storedKnown.value);
  saveError.value = "";
}

async function save(): Promise<void> {
  const list = [...unknownHidden.value, ...EMBER_WEB_PAGES.map((page) => page.id).filter((id) => draft.value.has(id))];
  saveError.value = "";
  saving.value = true;
  try {
    useStored((await settingsClient.setPages(list)).hidden);
    saved.value = true;
  } catch (err) {
    // The draft stays, so Save can be retried or Cancel drops it.
    saveError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="admin-panel">
    <p v-if="loadError" class="error">error: {{ loadError }}</p>
    <section class="card">
      <div class="head">
        <span v-if="stored && stored.length > 0" class="dot" title="Changed from the default" aria-hidden="true" />
        <h3>Sidebar pages</h3>
        <button v-if="anyHidden" type="button" class="small" :disabled="saving" @click="resetToDefault">Back to default</button>
        <span v-if="saved && !dirty" class="chip saved">Saved</span>
        <span class="chip scope">Applies to all accounts</span>
      </div>
      <ul v-if="stored" class="pages">
        <li v-for="page in EMBER_WEB_PAGES" :key="page.id" class="page-row">
          <ToggleSwitch
            :checked="!draft.has(page.id)"
            :disabled="saving"
            @change="setShown(page.id, ($event.target as HTMLInputElement).checked)"
          >
            <span class="page-name">{{ page.label }}</span>
          </ToggleSwitch>
        </li>
      </ul>
      <p class="muted">
        Show in the sidebar for everyone: turn a page off to remove its button from every account's sidebar, bottom bar
        and Overview. The page does not go away: it still opens from its address, and each account's permissions
        are unchanged. Chat and Settings always stay.
      </p>
      <div v-if="dirty" class="save-bar" role="group" aria-label="Unsaved change">
        <span class="dot" aria-hidden="true" />
        <span class="msg">You have an unsaved change. It applies to every account.</span>
        <button type="button" class="small" :disabled="saving" @click="cancel">Cancel</button>
        <button type="button" class="primary" :disabled="saving" @click="save">Save</button>
      </div>
      <p v-if="saveError" class="error">{{ saveError }}</p>
    </section>
  </div>
</template>

<style scoped>
.card {
  padding: 20px;
  background: var(--bg);
}
.card > .muted {
  max-width: 620px;
  font-size: 0.9em;
}
.card h3 {
  margin: 0;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
}
.chip.scope {
  margin-left: auto;
}
.chip.saved {
  color: var(--success);
  border-color: var(--success);
}
.pages {
  display: grid;
  gap: 10px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
}
.save-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.save-bar .msg {
  flex: 1 1 200px;
  font-size: 0.9em;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.card p {
  margin-bottom: 0;
}
</style>
