<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import "../../components/layout/infoPage.css";
import ListEditorLayout from "../../components/layout/ListEditorLayout.vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import { useUnsavedGuard } from "../../composables/useUnsavedGuard";
import { errorMessage } from "../../utils/errors";
import { brainClient, folderProblem, normalizeFolder, type BrainFile, type FileChanges } from "./api/BrainClient";
import FileEditor from "./components/FileEditor.vue";
import FileList from "./components/FileList.vue";
import { useBrainStore } from "./stores/brain";

/** The Notes page: the account's long-term memory as a file browser. A list on the left (folders, search,
 * files) and an editor on the right; on a narrow screen one at a time. Edits are a draft until Save. Agents
 * read every file; the editor has a switch that lets them edit one. */

const NEW = "new";
const store = useBrainStore();
const auth = useAuthStore();

// The open file: an id, NEW for one not saved yet, or null for none.
const selected = ref<string | null>(null);
// The version the editor holds as saved (its revision goes with every save); null for a new file.
const opened = ref<BrainFile | null>(null);
const opening = ref(false);
const openError = ref("");
let openRun = 0; // a late answer for a file the user has left is dropped
const form = reactive({ title: "", body: "", tags: [] as string[], folder: "", agentEditable: false });
const saved = reactive({ title: "", body: "", tags: [] as string[], folder: "", agentEditable: false });
const tagText = ref("");
const editor = ref<InstanceType<typeof FileEditor> | null>(null);
const listHost = ref<HTMLElement | null>(null);
// The newer version the server holds, while a refused save waits for the user's choice.
const conflict = ref<BrainFile | null>(null);
const saving = ref(false);
const removing = ref(false);
const reverting = ref(false);
const formError = ref("");
const notice = ref("");
const query = ref("");
const folder = ref<string | null>(null);

const busy = computed(() => saving.value || removing.value || reverting.value || opening.value);
const sameTags = (a: string[], b: string[]) => a.length === b.length && a.every((tag, i) => tag === b[i]);
const cleanFolder = computed(() => normalizeFolder(form.folder));
const problem = computed(() => folderProblem(cleanFolder.value));
// A tag typed but not added yet counts as an unsaved edit, so it is never lost silently.
const dirty = computed(
  () =>
    selected.value !== null &&
    !opening.value &&
    (form.title.trim() !== saved.title ||
      form.body !== saved.body ||
      cleanFolder.value !== saved.folder ||
      form.agentEditable !== saved.agentEditable ||
      !sameTags(form.tags, saved.tags) ||
      tagText.value.trim() !== ""),
);
const canSave = computed(() => (selected.value === NEW || opened.value !== null) && form.title.trim() !== "" && dirty.value && !busy.value && conflict.value === null && problem.value === "");
const canRevert = computed(() => opened.value?.edited === true && !dirty.value && !busy.value && conflict.value === null);
const revertHint = computed(() => (opened.value?.edited && dirty.value ? "Save or discard your changes first." : ""));

const maxChars = computed(() => store.summary?.max_record_chars ?? 20_000);
const knownTags = computed(() => {
  const counts = new Map<string, number>();
  for (const file of store.files) for (const tag of file.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  return [...counts]
    .filter(([tag]) => !form.tags.includes(tag))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tag, count]) => ({ tag, count }));
});

const shown = computed(() => {
  if (store.hits !== null) return store.hits;
  const wanted = folder.value;
  if (wanted === null) return store.files;
  return store.files.filter((f) => (wanted === "" ? f.folder === "" : f.folder === wanted || f.folder.startsWith(`${wanted}/`)));
});

function formatBytes(bytes: number): string {
  return bytes < 1_000_000 ? `${Math.round(bytes / 1000)} KB` : `${(bytes / 1_000_000).toFixed(1)} MB`;
}
const quotaLevel = computed<"" | "near" | "full">(() => {
  const s = store.summary;
  if (!s) return "";
  if (s.files >= s.max_files || s.bytes >= s.max_total_bytes) return "full";
  return s.files >= s.max_files * 0.8 || s.bytes >= s.max_total_bytes * 0.8 ? "near" : "";
});
const quotaText = computed(() => {
  const s = store.summary;
  return s ? `${s.files} of ${s.max_files} files · ${formatBytes(s.bytes)} of ${formatBytes(s.max_total_bytes)}` : "";
});
const headLabel = computed(() => {
  if (selected.value === NEW) return "New file";
  if (opened.value?.source === "automatic") return "Written by an agent";
  if (opened.value?.source === "shared") return "Shared with you";
  return "Your file";
});

// Search waits for a pause in typing; an empty box shows the list again.
let timer: ReturnType<typeof setTimeout> | undefined;
watch(query, (value) => {
  clearTimeout(timer);
  store.clearSearch();
  if (value.trim() && auth.account) timer = setTimeout(() => void store.search(value), 300);
}, { flush: "sync" });

onMounted(() => void store.load());
onBeforeUnmount(() => {
  resetPage();
  store.forget();
});

/** Fills the editor, and what counts as saved, from a file (or empty for a new one). */
function fillEditor(file: BrainFile | null, startFolder = ""): void {
  saved.title = form.title = file?.title ?? "";
  saved.body = form.body = file?.body ?? "";
  form.tags = [...(file?.tags ?? [])];
  saved.tags = [...form.tags];
  saved.folder = form.folder = file?.folder ?? startFolder;
  saved.agentEditable = form.agentEditable = file?.agent_editable ?? false;
  opened.value = file;
  conflict.value = null;
  tagText.value = "";
}

async function show(target: string | null): Promise<void> {
  if (!auth.account) return;
  const previous = selected.value;
  const run = ++openRun;
  selected.value = target;
  formError.value = "";
  notice.value = "";
  openError.value = "";
  opening.value = false;
  fillEditor(null, target === NEW ? (folder.value ?? "") : "");
  if (target !== null && target !== NEW) {
    opening.value = true;
    try {
      const file = await brainClient.get(target);
      if (run === openRun) fillEditor(file);
    } catch (err) {
      if (run === openRun) openError.value = errorMessage(err);
    } finally {
      if (run === openRun) opening.value = false;
    }
  }
  await nextTick();
  if (run !== openRun) return;
  if (target !== null) editor.value?.focusTitle();
  else (listHost.value?.querySelector<HTMLElement>(`[data-file-id="${previous}"]`) ?? listHost.value?.querySelector<HTMLElement>("input"))?.focus();
}

// Leaving unsaved edits asks first; the target waits here meanwhile.
const discardTarget = ref<string | null | undefined>(undefined);
function go(target: string | null): void {
  if (!auth.account || busy.value || target === selected.value) return;
  if (dirty.value) discardTarget.value = target;
  else void show(target);
}
function discard(): void {
  const target = discardTarget.value;
  discardTarget.value = undefined;
  if (target !== undefined) void show(target);
}

// Leaving the page with unsaved edits asks first, like the Settings page.
const { open: leaveOpen, answer: answerLeave } = useUnsavedGuard({ dirty: () => dirty.value, busy: () => busy.value });

function startNew(): void {
  if (!auth.account || store.status !== "ready") return;
  if (quotaLevel.value === "full") {
    notice.value = "Your brain is full. Delete a file, or ask an administrator to raise the limit.";
    return;
  }
  go(NEW);
}

function changesFromEditor(): FileChanges {
  const changes: FileChanges = {};
  if (form.title.trim() !== saved.title) changes.title = form.title.trim();
  if (form.body !== saved.body) changes.body = form.body;
  if (!sameTags(form.tags, saved.tags)) changes.tags = [...form.tags];
  if (cleanFolder.value !== saved.folder) changes.folder = cleanFolder.value;
  if (form.agentEditable !== saved.agentEditable) changes.agent_editable = form.agentEditable;
  return changes;
}

async function save(): Promise<void> {
  const id = selected.value;
  const revision = opened.value?.revision;
  if (!auth.account || id === null || busy.value) return;
  const run = openRun;
  editor.value?.commitTags(); // a tag still in the box is part of the file
  if (tagText.value.trim() !== "") return; // it could not be added (too many tags): its message is showing
  if (!canSave.value || (id !== NEW && revision === undefined)) return;
  saving.value = true;
  formError.value = "";
  try {
    const record =
      revision === undefined
        ? await store.create({ title: form.title.trim(), body: form.body, tags: [...form.tags], folder: cleanFolder.value })
        : await store.save(id, changesFromEditor(), revision);
    if (run !== openRun) return;
    selected.value = record.id;
    fillEditor(record);
    notice.value = "Saved.";
  } catch (err) {
    if (run !== openRun) return;
    if (err instanceof ApiError && err.status === 412 && id !== NEW) await loadConflict(id, run);
    else formError.value = errorMessage(err);
  } finally {
    if (run === openRun) saving.value = false;
  }
}

/** The server refused because the file changed: fetch its newer version and ask what to do. */
async function loadConflict(id: string, run: number): Promise<void> {
  try {
    const latest = await brainClient.get(id);
    if (run === openRun) conflict.value = latest;
  } catch (err) {
    if (run === openRun) formError.value = errorMessage(err);
  }
}
/** Drops the user's edits for the newer version. */
function showTheirs(): void {
  const theirs = conflict.value;
  if (theirs === null) return;
  fillEditor(theirs);
  notice.value = "Showing the newer version.";
  void store.load();
}
/** Saves the user's edits over the newer version: only the fields the user changed are sent. */
async function keepMine(): Promise<void> {
  const theirs = conflict.value;
  if (theirs === null) return;
  opened.value = theirs;
  conflict.value = null;
  await save();
}

const confirmRevert = ref(false);
async function revert(): Promise<void> {
  const file = opened.value;
  if (!auth.account || file === null || !canRevert.value) return;
  const run = openRun;
  reverting.value = true;
  formError.value = "";
  try {
    const restored = await store.revert(file.id, file.revision);
    if (run !== openRun) return;
    fillEditor(restored);
    notice.value = "Original text restored.";
  } catch (err) {
    if (run !== openRun) return;
    if (err instanceof ApiError && err.status === 412) await loadConflict(file.id, run);
    else formError.value = errorMessage(err);
  } finally {
    if (run === openRun) {
      reverting.value = false;
      confirmRevert.value = false;
    }
  }
}

const confirmDelete = ref(false);
async function remove(): Promise<void> {
  const id = selected.value;
  if (!auth.account || id === null || id === NEW || busy.value) return;
  const run = openRun;
  removing.value = true;
  formError.value = "";
  try {
    await store.remove(id);
    if (run !== openRun) return;
    removing.value = false;
    confirmDelete.value = false;
    void show(null);
    notice.value = "File deleted.";
  } catch (err) {
    if (run !== openRun) return;
    formError.value = errorMessage(err);
    removing.value = false;
    confirmDelete.value = false;
  }
}

function resetPage(): void {
  ++openRun;
  clearTimeout(timer);
  selected.value = null;
  opening.value = saving.value = removing.value = reverting.value = false;
  openError.value = formError.value = notice.value = "";
  discardTarget.value = undefined;
  confirmDelete.value = confirmRevert.value = false;
  answerLeave(false);
  query.value = "";
  folder.value = null;
  fillEditor(null);
}

watch(() => auth.account?.id, () => {
  resetPage();
  if (auth.account) void store.load();
}, { flush: "sync" });
</script>

<template>
  <PageLayout class="notes info-content" :class="{ 'file-open': selected !== null }" title="Notes" description="Your long-term memory: the files you and your agents keep." wide fill>
    <template #actions>
      <button type="button" class="primary new-file" :disabled="busy || store.status !== 'ready'" @click="startNew">New file</button>
    </template>
    <div class="column">
      <p v-if="quotaText" class="quota" :class="quotaLevel" data-test="quota">
        <svg v-if="quotaLevel" class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        {{ quotaText }}<template v-if="quotaLevel === 'full'"> · full</template><template v-else-if="quotaLevel === 'near'"> · nearly full</template>
      </p>
      <p v-if="store.summary?.skipped" class="muted skipped" role="status">
        {{ store.summary.skipped }} {{ store.summary.skipped === 1 ? "file" : "files" }} in your brain folder could not be read and {{ store.summary.skipped === 1 ? "is" : "are" }} not shown.
      </p>
      <p v-if="notice" class="notice-line" role="status">{{ notice }}</p>
      <p v-if="store.status === 'ready' && store.error" class="error" role="alert">Could not refresh your files: {{ store.error }}</p>
      <StateMessage v-if="store.status === 'idle' || store.status === 'loading'" kind="loading">Loading …</StateMessage>
      <StateMessage v-else-if="store.status === 'error'" kind="error" @retry="store.load()">Could not load your files: {{ store.error }}</StateMessage>

      <ListEditorLayout
        v-else
        class="layout"
        :editing="selected !== null"
        list-label="Files list"
        editor-label="File editor"
        back-label="All files"
        visible-scrollbars
        :busy="busy"
        :saving="saving"
        :dirty="dirty"
        :can-save="canSave"
        @back="go(null)"
        @submit="save"
      >
        <template #list>
          <div ref="listHost" class="list-host">
            <FileList
              v-model:query="query"
              v-model:folder="folder"
              :rows="shown"
              :folders="store.folders"
              :selected-id="selected === NEW ? null : selected"
              :draft-title="selected === NEW ? form.title : null"
              :is-search="store.hits !== null"
              :search-busy="store.searching"
              :search-error="store.searchError"
              :disabled="busy"
              @select="go"
            />
          </div>
        </template>

        <template #head>
          <span class="context-label"><svg class="line-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>{{ headLabel }}</span>
        </template>

        <template #editor>
          <StateMessage v-if="opening" kind="loading">Opening …</StateMessage>
          <StateMessage v-else-if="openError" kind="error" @retry="selected !== null && show(selected)">Could not open this file: {{ openError }}</StateMessage>
          <template v-else>
            <FileEditor
              :key="selected ?? ''"
              ref="editor"
              v-model:title="form.title"
              v-model:body="form.body"
              v-model:tags="form.tags"
              v-model:tagText="tagText"
              v-model:folder="form.folder"
              v-model:agentEditable="form.agentEditable"
              :file="opened"
              :folders="store.folders"
              :known-tags="knownTags"
              :max-chars="maxChars"
              :folder-problem="problem"
              :can-revert="canRevert"
              :revert-hint="revertHint"
              :disabled="busy"
              @revert="confirmRevert = true"
              @remove="confirmDelete = true"
            />
            <p v-if="formError" class="error form-error" role="alert">{{ formError }}</p>
            <div v-if="conflict" class="conflict" role="alert">
              <p>{{ conflict.last_editor === "agent" ? "An agent" : "Another session" }} changed this file after you opened it.</p>
              <div class="conflict-actions">
                <button type="button" class="chip" @click="showTheirs">Show their version (drops my changes)</button>
                <button v-if="dirty" type="button" class="chip" @click="keepMine">Save mine anyway</button>
              </div>
            </div>
          </template>
        </template>

        <template #placeholder>
          <svg class="line-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>
          <h3>What you and your agents remember</h3>
          <p>Pick a file, or start a new one.</p>
          <button type="button" class="chip" @click="startNew">Create a file</button>
        </template>
      </ListEditorLayout>
    </div>

    <ConfirmModal
      :open="confirmDelete"
      title="Delete this file?"
      message="This file will be gone for good, with the saved original text if it has one."
      confirm-label="Delete file"
      danger
      :busy="removing"
      @confirm="remove"
      @close="confirmDelete = false"
    />
    <ConfirmModal
      :open="confirmRevert"
      title="Restore the original text?"
      message="The text, title and tags from before your first change come back. Your changes are replaced."
      confirm-label="Restore original"
      danger
      :busy="reverting"
      @confirm="revert"
      @close="confirmRevert = false"
    />
    <ConfirmModal
      :open="leaveOpen"
      title="Leave without saving?"
      message="This file has changes you have not saved."
      confirm-label="Leave page"
      danger
      @confirm="answerLeave(true)"
      @close="answerLeave(false)"
    />
    <ConfirmModal
      :open="discardTarget !== undefined"
      title="Discard your changes?"
      message="This file has changes you have not saved."
      confirm-label="Discard"
      danger
      @confirm="discard"
      @close="discardTarget = undefined"
    />
  </PageLayout>
</template>

<style scoped src="../../components/layout/editorPage.css"></style>
<style scoped>
.layout { --workspace-columns: 360px minmax(0, 1fr); }
.layout :deep(.list-pane) { overflow: hidden; }
.column { display: flex; flex: 1; min-height: 0; flex-direction: column; }
.list-host { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.new-file { flex-shrink: 0; min-height: 40px; }
.quota { display: flex; align-items: center; gap: 6px; margin: 0 0 8px; font-size: .85em; color: var(--muted); font-variant-numeric: tabular-nums; }
.quota.near .line-icon { color: var(--warning); }
.quota.full .line-icon { color: var(--danger); }
.skipped, .notice-line { margin: 0 0 8px; font-size: .85em; }
.conflict { display: flex; flex-direction: column; gap: 8px; margin: 12px 20px; padding: 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .9em; }
.conflict p { margin: 0; }
.conflict-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.conflict-actions button { overflow-wrap: anywhere; }
.form-error { margin: 12px 20px; }
.notes :deep(.error), .notes :deep(button.danger) { color: var(--text); }
@media (max-width: 900px) and (min-width: 768px) { .notes .layout { --workspace-columns: 280px minmax(0, 1fr); } }
@media (max-width: 767px) {
  .notes :deep(.page-column) { padding: 18px 16px 12px; }
  .notes :deep(.page-head) { flex-direction: row; align-items: center; margin-bottom: 16px; gap: 10px; }
  .notes :deep(.page-title) { margin: 0; }
  .notes :deep(.page-description) { display: none; }
  .notes :deep(.page-actions button) { min-width: 44px; min-height: 44px; }
  .notes.file-open :deep(.page-head) { display: none; }
  .conflict-actions button, .layout button.chip,
  .notes :deep(.state button), .notes :deep(dialog .actions button),
  .notes :deep(.file-editor [role="option"]) { min-width: 44px; min-height: 44px; }
}
</style>
