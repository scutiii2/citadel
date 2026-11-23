<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { settingsClient, type AppSettings } from "../../api/SettingsClient";
import { useDraftPanel } from "../../composables/useDraftPanel";
import { errorMessage } from "../../utils/errors";
import LockSwitch from "../LockSwitch.vue";
import AdminSearch from "./AdminSearch.vue";
import ConfirmModal from "./ConfirmModal.vue";
import DraftActions from "./DraftActions.vue";
import "./admin.css";

/** Tool approval: one setting that reaches every account, so a flip is a draft until Save. Search only
 * filters what is shown; the draft stays mounted. */
const emit = defineEmits<{ modified: [value: boolean] }>();

const SEARCHABLE = "tool approval require approval every tool allow once allow for this chat typed commands";
const settings = ref<AppSettings | null>(null);
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);
const draft = ref(false);
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const dirty = computed(() => settings.value !== null && draft.value !== settings.value.force_tool_approval);
const matches = computed(() => !search.value.trim() || SEARCHABLE.includes(search.value.trim().toLowerCase()));
const { discardOpen, keepFocus, answerDiscard } = useDraftPanel(dirty, searchField);

async function load(): Promise<void> {
  loadError.value = "";
  try {
    settings.value = await settingsClient.get();
    draft.value = settings.value.force_tool_approval;
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

function setDraft(box: HTMLInputElement): void {
  draft.value = box.checked;
  saved.value = false;
  saveError.value = "";
}

// The stored value is what counts as changed; a draft only becomes one once saved.
const storedOn = computed(() => settings.value?.force_tool_approval === true);
watch(storedOn, (on) => emit("modified", on), { immediate: true });

/** Puts the switch back to the default (off). Like any flip it is a draft until Save. */
function resetToDefault(): void {
  draft.value = false;
  saved.value = false;
  saveError.value = "";
}

function cancel(): void {
  draft.value = settings.value?.force_tool_approval ?? false;
  saveError.value = "";
}

async function save(): Promise<void> {
  const on = draft.value;
  saveError.value = "";
  saving.value = true;
  await keepFocus(async () => {
    try {
      await settingsClient.set("force_tool_approval", on);
      if (settings.value) settings.value = { ...settings.value, force_tool_approval: on };
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
  <section class="admin-panel-card settings-panel admin-panel" aria-labelledby="tool-approval-title">
    <header class="admin-panel-head">
      <h2 id="tool-approval-title"><span v-if="storedOn" class="dot" title="Changed from the default" aria-hidden="true" /> Tool approval</h2>
      <div class="admin-panel-tools tools">
        <DraftActions :dirty="dirty" :saving="saving" label="tool approval changes" @cancel="discardOpen = true" @save="save" />
        <AdminSearch ref="searchField" v-model="search" label="Search tool approval" />
      </div>
    </header>
    <p v-if="loadError" class="admin-panel-text error" role="alert">{{ loadError }}</p>
    <p v-if="!matches" class="admin-panel-text muted">No settings match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
    <div v-show="matches" class="body">
      <div class="meta">
        <span class="chip scope">Applies to all accounts</span>
        <button v-if="draft" type="button" class="small" :disabled="saving" @click="resetToDefault">Back to default</button>
        <span v-if="saved && !dirty" class="chip saved" role="status">Saved</span>
      </div>
      <LockSwitch v-if="settings" :checked="draft" :disabled="saving" @change="setDraft($event.target as HTMLInputElement)">Require approval for every tool</LockSwitch>
      <p class="muted">
        When on, every account's answers ask before each tool the agent runs, whatever the account chose, and "Allow
        for this chat" is not offered. A tool runs only after its own "Allow once". Typed commands (such as /tool) are
        not affected: the person types the exact command themselves.
      </p>
      <p v-if="dirty" class="unsaved" role="status">You have an unsaved change. Turning it {{ draft ? "on" : "off" }} applies to every account.</p>
      <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
    </div>
    <ConfirmModal :open="discardOpen" title="Discard unsaved change?" message="Your tool approval change has not been saved." confirm-label="Discard change" @confirm="answerDiscard(true, cancel)" @close="answerDiscard(false, cancel)" />
  </section>
</template>

<style scoped>
.settings-panel { margin-bottom: 14px; }
.body { display: grid; gap: 10px; padding: 14px; }
.body p { margin: 0; }
.body > .muted { max-width: 620px; font-size: 0.9em; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.chip.saved { color: var(--success); border-color: var(--success); }
.unsaved { font-size: 0.9em; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: var(--radius-full); background: var(--accent); }
.tools { flex-wrap: nowrap; }
</style>
