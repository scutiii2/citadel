<script setup lang="ts">
import ActionMessage from "./ActionMessage.vue";
import { computed, onMounted, ref } from "vue";
import { settingsClient } from "../../api/SettingsClient";
import { useDraftPanel } from "../../composables/useDraftPanel";
import { EMBER_WEB_PAGES } from "../../utils/emberWebPages";
import { errorMessage } from "../../utils/errors";
import ToggleSwitch from "../ToggleSwitch.vue";
import AdminSearch from "./AdminSearch.vue";
import FieldLabel from "./FieldLabel.vue";
import PanelHelp from "./PanelHelp.vue";
import ConfirmModal from "./ConfirmModal.vue";
import DraftActions from "./DraftActions.vue";
import "./admin.css";

/** Which ember_web pages every user's sidebar shows. Hiding is nav only: a hidden page still opens
 * by its address. A flip is a draft until Save; search only filters the rows, the draft stays mounted. */
const known = new Set<string>(EMBER_WEB_PAGES.map((page) => page.id));
const stored = ref<string[] | null>(null);
// The pages the draft hides, among the ones listed here.
const draft = ref<Set<string>>(new Set());
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();

/** Ids ember_web may know but this page does not list: kept as they are on every save. */
const unknownHidden = computed(() => (stored.value ?? []).filter((id) => !known.has(id)));
const storedKnown = computed(() => new Set((stored.value ?? []).filter((id) => known.has(id))));
const dirty = computed(
  () => stored.value !== null && (draft.value.size !== storedKnown.value.size || [...draft.value].some((id) => !storedKnown.value.has(id))),
);
const anyHidden = computed(() => draft.value.size > 0 || unknownHidden.value.length > 0);
const shownPage = (label: string) => !search.value.trim() || label.toLowerCase().includes(search.value.trim().toLowerCase());
const matchCount = computed(() => EMBER_WEB_PAGES.filter((page) => shownPage(page.label)).length);
const { discardOpen, keepFocus, answerDiscard } = useDraftPanel(dirty, searchField);

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
  await keepFocus(async () => {
    try {
      useStored((await settingsClient.setPages(list)).hidden);
      saved.value = true;
    } catch (err) {
      // The draft stays, so Save can be retried or Cancel drops it.
      saveError.value = errorMessage(err);
    } finally {
      saving.value = false;
    }
  });
}

onMounted(load);
</script>

<template>
  <section class="admin-panel-card sidebar-panel admin-panel" aria-labelledby="sidebar-pages-title">
    <header class="admin-panel-head">
      <h2 id="sidebar-pages-title"><span v-if="stored && stored.length > 0" class="dot" title="Changed from the default" aria-hidden="true" /> Ember menu</h2>
      <div class="admin-panel-tools tools">
        <PanelHelp title="Ember menu"><p>Chooses which pages appear in the menu of the Ember app for every user. Edit, then Save to apply it to everyone.</p><p>Turn a page off to remove its button from every user's sidebar, bottom bar and Overview. The page does not go away: it still opens from its address, and each user's permissions are unchanged. Chat and Settings always stay.</p></PanelHelp>
        <DraftActions :dirty="dirty" :saving="saving" label="Ember menu changes" @cancel="discardOpen = true" @save="save" />
        <AdminSearch ref="searchField" v-model="search" label="Search menu pages" />
      </div>
    </header>
    <ActionMessage v-if="loadError" kind="error" :text="loadError" class="admin-panel-text" />
    <p v-if="stored && !matchCount" class="admin-panel-text muted">No pages match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
    <div class="body">
      <div class="meta">
        <span class="chip scope">Applies to all users</span>
        <button v-if="anyHidden" type="button" class="small" :disabled="saving" @click="resetToDefault">Back to default</button>
        <ActionMessage v-if="saved && !dirty" kind="ok" text="Saved" />
      </div>
      <ul v-if="stored" class="pages">
        <li v-for="page in EMBER_WEB_PAGES" v-show="shownPage(page.label)" :key="page.id" class="page-row">
          <ToggleSwitch :checked="!draft.has(page.id)" :disabled="saving" @change="setShown(page.id, ($event.target as HTMLInputElement).checked)">
            <span class="page-name">{{ page.label }}</span>
          </ToggleSwitch>
          <FieldLabel bare :title="page.label"><p><b>On:</b> {{ page.label }} has a button in the Ember menu, bottom bar and Overview for every user who may open it.</p><p><b>Off:</b> the button is hidden for everyone. The page still opens from its address and permissions do not change.</p></FieldLabel>
        </li>
      </ul>
      <p v-if="dirty" class="unsaved" role="status">You have an unsaved change. It applies to every user.</p>
      <ActionMessage v-if="saveError" kind="error" :text="saveError" />
    </div>
    <ConfirmModal :open="discardOpen" title="Discard unsaved changes?" message="Your sidebar page changes have not been saved." confirm-label="Discard changes" @confirm="answerDiscard(true, cancel)" @close="answerDiscard(false, cancel)" />
  </section>
</template>

<style scoped>
.sidebar-panel { margin-bottom: 14px; }
.body { display: grid; gap: 10px; padding: 14px; }
.body p { margin: 0; }
.body > .muted { max-width: 620px; font-size: 0.9em; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.chip.saved { color: var(--success); border-color: var(--success); }
.pages { display: grid; margin: 0; padding: 0; list-style: none; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.page-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 14px; }
.page-row + .page-row { border-top: 1px solid var(--border); }
.unsaved { font-size: 0.9em; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: var(--radius-full); background: var(--accent); }
.tools { flex-wrap: nowrap; }
</style>
