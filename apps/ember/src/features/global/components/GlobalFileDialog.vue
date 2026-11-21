<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { isApiStatus } from "../../../api/http";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import CharacterCount from "../../../components/ui/status/CharacterCount.vue";
import DangerZone from "../../../components/ui/status/DangerZone.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import { FILE_TITLE_MAX, folderProblem, normalizeFolder, type BrainFile } from "../../notes/api/BrainClient";
import { globalClient, type GlobalFileChanges } from "../api/GlobalClient";

const props = defineProps<{ open: boolean; fileId: string | null; canWrite: boolean; maxChars: number }>();
const emit = defineEmits<{ close: []; done: [message: string] }>();
const auth = useAuthStore();
const loaded = ref<BrainFile | null>(null);
const title = ref("");
const body = ref("");
const folder = ref("");
const loadError = ref("");
const error = ref("");
const busy = ref(false);
const stale = ref(false);
const confirmDelete = ref(false);
let run = 0;

const cleanFolder = computed(() => normalizeFolder(folder.value));
const problem = computed(() => folderProblem(cleanFolder.value));
const tooLong = computed(() => body.value.length > props.maxChars);
const changes = computed(() => {
  const change: GlobalFileChanges = {};
  if (loaded.value && title.value.trim() !== loaded.value.title) change.title = title.value.trim();
  if (loaded.value && body.value !== loaded.value.body) change.body = body.value;
  if (loaded.value && cleanFolder.value !== loaded.value.folder) change.folder = cleanFolder.value;
  return change;
});
const canSave = computed(() => props.open && props.canWrite && !busy.value && !stale.value &&
  !!title.value.trim() && title.value.trim().length <= FILE_TITLE_MAX && !problem.value && !tooLong.value &&
  (props.fileId === null || Object.keys(changes.value).length > 0));

function clear(): void {
  run++;
  loaded.value = null;
  title.value = body.value = folder.value = loadError.value = error.value = "";
  busy.value = stale.value = confirmDelete.value = false;
}
function close(): void {
  clear();
  emit("close");
}
watch(() => auth.account?.id, close, { flush: "sync" });
onBeforeUnmount(clear);
watch(() => [props.open, props.fileId] as const, async ([open, id]) => {
  clear();
  if (!open || id === null) return;
  const current = run;
  try {
    const file = await globalClient.get(id);
    if (current !== run) return;
    loaded.value = file;
    title.value = file.title;
    body.value = file.body;
    folder.value = file.folder;
  } catch (err) {
    if (current === run) loadError.value = errorMessage(err);
  }
}, { immediate: true, flush: "sync" });

async function write(work: () => Promise<unknown>, message: string): Promise<void> {
  const current = run;
  busy.value = true;
  error.value = "";
  try {
    await work();
    if (current !== run) return;
    clear();
    emit("done", message);
  } catch (err) {
    if (current !== run) return;
    stale.value = isApiStatus(err, 412);
    error.value = stale.value
      ? "This file changed since someone opened it. Close it and open it again."
      : errorMessage(err);
    confirmDelete.value = false;
  } finally {
    if (current === run) busy.value = false;
  }
}

function save(): void {
  if (!canSave.value) return;
  const file = loaded.value;
  if (file) void write(() => globalClient.update(file.id, changes.value, file.revision), "Saved.");
  else void write(() => globalClient.create({ title: title.value.trim(), body: body.value, folder: cleanFolder.value }), "Created.");
}

function remove(): void {
  const file = loaded.value;
  if (!file || !props.open || !props.canWrite || busy.value || stale.value || !confirmDelete.value) return;
  void write(() => globalClient.remove(file.id), "Deleted.");
}
</script>

<template>
  <BaseModal :open="open" :title="fileId === null ? 'New global file' : 'Global file'" wide @close="close">
    <div v-if="open" class="file-dialog">
      <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
      <p v-else-if="fileId !== null && !loaded" role="status">Loading file…</p>
      <form v-else-if="canWrite" class="dialog-form" @submit.prevent="save">
        <label class="field">
          <span class="label">Title</span>
          <input v-model="title" aria-label="Title" type="text" :maxlength="FILE_TITLE_MAX" :disabled="busy || stale" required />
        </label>
        <label class="field">
          <span class="label">Folder</span>
          <input v-model="folder" aria-label="Folder" type="text" maxlength="130" :disabled="busy || stale"
            :aria-invalid="!!problem" :aria-describedby="problem ? 'global-file-folder-problem' : undefined" />
        </label>
        <p v-if="problem" id="global-file-folder-problem" class="error problem" role="alert">
          <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
          {{ problem }}
        </p>
        <label class="field">
          <span class="label">Text</span>
          <textarea v-model="body" aria-label="Text" rows="9" :disabled="busy || stale" :aria-invalid="tooLong"
            :aria-describedby="tooLong ? 'global-file-count global-file-text-problem' : 'global-file-count'" />
        </label>
        <CharacterCount id="global-file-count" :length="body.length" :max="maxChars" suffix=" characters" />
        <p v-if="tooLong" id="global-file-text-problem" class="error problem" role="alert">
          <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
          Text must be {{ maxChars }} characters or fewer.
        </p>
        <p v-if="error" class="error problem" role="alert">
          <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
          {{ error }}
        </p>
        <div class="buttons">
          <button type="button" class="pill-btn ghost" @click="close">Close</button>
          <button class="pill-btn primary" type="submit" :disabled="!canSave" :aria-busy="busy && !confirmDelete" @click.prevent="save">
            {{ fileId === null ? "Create" : "Save" }}
          </button>
        </div>
        <DangerZone v-if="loaded && !stale" label="Permanently delete this global file">
          <button type="button" class="pill-btn ghost" :disabled="busy" @click="confirmDelete = true">Delete</button>
        </DangerZone>
      </form>
      <template v-else-if="loaded">
        <h4>{{ loaded.title }}</h4>
        <p class="meta">{{ loaded.folder || "Top folder" }} · Updated {{ formatUtc(loaded.updated_at) }}</p>
        <pre class="text">{{ loaded.body }}</pre>
        <div class="buttons"><button type="button" class="pill-btn ghost" @click="close">Close</button></div>
      </template>
    </div>
  </BaseModal>
  <ConfirmModal v-if="confirmDelete && canWrite" :open="open" title="Delete global file?" message="This removes the file for everyone."
    danger confirm-label="Delete" :busy="busy" @close="confirmDelete = false" @confirm="remove" />
</template>

<style scoped>
.file-dialog { display: flex; flex-direction: column; gap: 12px; }
.file-dialog .error { color: var(--text); }
p, h4 { margin: 0; overflow-wrap: anywhere; }
.meta, .label { font-size: .85em; color: var(--muted); }
.text { margin: 0; max-height: 40dvh; overflow: auto; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--code-bg); font: inherit; font-size: .9em; white-space: pre-wrap; overflow-wrap: anywhere; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field :is(input, textarea) { min-height: 44px; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.problem { display: flex; align-items: flex-start; gap: 8px; }
.problem .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.buttons button, .danger-panel button { min-height: 44px; }
@media (max-width: 767px) {
  .field :is(input, textarea) { font-size: max(1em, 16px); }
}
</style>
