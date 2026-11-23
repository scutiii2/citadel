<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import RecordDrawer from "../../../components/ui/panel/RecordDrawer.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import { FILE_TITLE_MAX, folderProblem, normalizeFolder } from "../../notes/api/BrainClient";
import { proposalsClient, type Proposal, type ProposalDetail } from "../api/ProposalsClient";
import { isDecidedProposalError, useProposalsStore } from "../stores/proposals";

/** What agents suggested for long-term memory. A list, then one suggestion at a time: its text as plain text, an editable
 * title and folder, and Keep or Decline. Opening one changes nothing. The text is an agent's, so it is never shown as
 * markup and is dropped when the person goes back or this closes. Render it only while open (`v-if`). */
defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; done: [message: string] }>();

const store = useProposalsStore();
const auth = useAuthStore();
const chosen = ref<Proposal | null>(null);
const backButton = ref<HTMLButtonElement | null>(null);
const list = ref<HTMLUListElement | null>(null);
const detail = ref<ProposalDetail | null>(null);
const loadError = ref("");
const title = ref("");
const folder = ref("");
const removeItems = ref(true);
const busy = ref(false);
const error = ref("");
let run = 0; // a late answer for a suggestion the person has left is dropped

const cleanFolder = computed(() => normalizeFolder(folder.value));
const problem = computed(() => folderProblem(cleanFolder.value));
const canKeep = computed(() => detail.value !== null && title.value.trim() !== "" && problem.value === "" && !busy.value);

function reset(): void {
  run++;
  chosen.value = null;
  detail.value = null;
  title.value = folder.value = error.value = loadError.value = "";
  removeItems.value = true;
  busy.value = false;
}
function close(): void {
  if (busy.value) return;
  reset();
  emit("close");
}

function back(): void {
  const id = chosen.value?.id;
  reset();
  void nextTick(() => {
    const rows = list.value?.querySelectorAll<HTMLButtonElement>("[data-suggestion]") ?? [];
    Array.from(rows).find((row) => row.dataset.suggestion === id)?.focus();
  });
}

onBeforeUnmount(reset);
watch(() => auth.account?.id, () => { reset(); emit("close"); }, { flush: "sync" });

async function choose(proposal: Proposal): Promise<void> {
  reset();
  const mine = run;
  chosen.value = proposal;
  title.value = proposal.title;
  folder.value = proposal.folder;
  void nextTick(() => { if (mine === run) backButton.value?.focus(); });
  try {
    const found = await proposalsClient.get(proposal.id);
    if (mine !== run) return;
    if (found.status !== "pending") {
      loadError.value = "That suggestion is already decided.";
      void store.load();
      return;
    }
    detail.value = found;
    title.value = found.title;
    folder.value = found.folder;
  } catch (err) {
    if (mine === run) loadError.value = errorMessage(err);
  }
}

async function answer(work: () => Promise<string>): Promise<void> {
  if (busy.value || !detail.value) return;
  const mine = run;
  busy.value = true;
  error.value = "";
  try {
    const message = await work();
    if (mine === run) {
      reset();
      emit("done", message);
    }
  } catch (err) {
    if (mine === run) {
      error.value = errorMessage(err);
      if (isDecidedProposalError(err)) detail.value = null;
    }
  } finally {
    if (mine === run) busy.value = false;
  }
}

function keep(): void {
  if (!canKeep.value || !chosen.value) return;
  const proposal = chosen.value;
  void answer(async () => {
    const wanted = proposal.item_ids.length > 0 && removeItems.value;
    const done = await store.accept(proposal.id, { title: title.value.trim(), folder: cleanFolder.value, remove_items: wanted });
    const moved = done.removed > 0 ? ` ${done.removed} ${done.removed === 1 ? "item was" : "items were"} removed from short-term memory.` : "";
    return `Kept as a file${cleanFolder.value ? ` in ${cleanFolder.value}` : ""}.${moved}`;
  });
}
function decline(): void {
  if (!chosen.value) return;
  const id = chosen.value.id;
  void answer(async () => { await store.decline(id); return "Declined."; });
}
</script>

<template>
  <RecordDrawer :open="open" class="proposal-review" title="Suggestions from your agents" @close="close">
    <div v-if="open" class="suggestions">
      <template v-if="!chosen">
        <StateMessage v-if="store.status === 'idle' || store.status === 'loading'" kind="loading">Loading …</StateMessage>
        <StateMessage v-else-if="store.status === 'error'" kind="error" @retry="store.load()">
          <span class="problem"><svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg> Could not load suggestions: {{ store.error }}</span>
        </StateMessage>
        <StateMessage v-else-if="store.items.length === 0" kind="empty">No suggestions are waiting.</StateMessage>
        <ul v-else ref="list" class="list">
          <li v-for="item in store.items" :key="item.id">
            <button type="button" class="row" :data-suggestion="item.id" @click="choose(item)">
              <span class="name">{{ item.title }}</span>
              <span class="meta">{{ formatUtc(item.created_at) }} · {{ item.chars }} characters</span>
            </button>
          </li>
        </ul>
      </template>
      <template v-else>
        <p v-if="loadError" class="error problem" role="alert"><svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg> {{ loadError }}</p>
        <StateMessage v-else-if="!detail && !error" kind="loading">Loading …</StateMessage>
        <template v-else-if="detail">
          <p class="untrusted" role="note">
            <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
            {{ detail.notice }}
          </p>
          <pre class="text">{{ detail.body }}</pre>
          <label class="field"><span class="label">Title</span><input v-model="title" type="text" aria-label="Title" :maxlength="FILE_TITLE_MAX" :disabled="busy" /></label>
          <label class="field"><span class="label">Keep it in folder</span><input v-model="folder" type="text" aria-label="Folder" maxlength="130" :disabled="busy" :aria-invalid="!!problem" :aria-describedby="problem ? 'suggestion-folder-problem' : undefined" /></label>
          <p v-if="problem" id="suggestion-folder-problem" class="error problem" role="alert"><svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg> {{ problem }}</p>
          <ToggleSwitch v-if="chosen.item_ids.length > 0" class="check" :checked="removeItems" :disabled="busy" @change="removeItems = ($event.target as HTMLInputElement).checked">Also remove the source items from short-term memory</ToggleSwitch>
        </template>
        <p v-if="error" class="error problem" role="alert"><svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg> {{ error }}</p>
      </template>
      <div class="buttons">
        <button v-if="chosen" ref="backButton" type="button" class="pill-btn ghost" :disabled="busy" @click="back">Back</button>
        <button type="button" class="pill-btn ghost" :disabled="busy" @click="close">Close</button>
        <template v-if="chosen">
          <button type="button" class="pill-btn ghost" :disabled="busy || !detail" @click="decline">Decline</button>
          <button type="button" class="pill-btn primary" :disabled="!canKeep" :aria-busy="busy" @click="keep">Keep</button>
        </template>
      </div>
    </div>
  </RecordDrawer>
</template>

<style scoped>
.suggestions .error { color: var(--text); }
.suggestions { display: flex; flex-direction: column; gap: 12px; }
p { margin: 0; overflow-wrap: anywhere; }
.meta { font-size: .9em; color: var(--muted); }
.untrusted { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .85em; }
.untrusted .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.text { margin: 0; max-height: 40dvh; overflow: auto; scrollbar-gutter: stable; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--code-bg); font: inherit; font-size: .9em; white-space: pre-wrap; overflow-wrap: anywhere; }
.field { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: .85em; color: var(--muted); }
.field input { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px; }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.row { width: 100%; min-height: 44px; display: grid; gap: 2px; text-align: left; padding: 8px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); cursor: pointer; overflow-wrap: anywhere; }
.row .name { font-weight: 600; }
.check { display: flex; align-items: center; gap: 8px; min-height: 44px; }
.problem { display: flex; align-items: flex-start; gap: 8px; }
.problem .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.field input, .buttons button, .suggestions :deep(.chip), .proposal-review :deep(header .close) { min-height: 44px; }
.proposal-review :deep(header .close) { min-width: 44px; }
@media (max-width: 767px) {
  .field input { font-size: max(1em, 16px); }
}
</style>
