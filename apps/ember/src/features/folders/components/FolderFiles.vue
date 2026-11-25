<script setup lang="ts">
import { ref } from "vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { errorMessage } from "../../../utils/errors";
import { formatBytes } from "../../../utils/format";
import { formatUtc } from "../../../utils/time";
import { foldersClient, type FolderFile } from "../api/FoldersClient";

/** The files of one folder and the control that adds more. Anyone with the link may download and add;
 * only the owner's page passes `removable`, which shows the remove button. */
const props = defineProps<{ token: string; files: FolderFile[]; maxFileBytes: number; removable?: boolean }>();
const emit = defineEmits<{ added: []; remove: [file: FolderFile] }>();

const picker = ref<HTMLInputElement | null>(null);
const busy = ref(false);
const error = ref("");

async function upload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const chosen = Array.from(input.files ?? []);
  input.value = "";
  if (!chosen.length || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    for (const file of chosen) {
      if (file.size > props.maxFileBytes) throw new Error(`${file.name} is over ${formatBytes(props.maxFileBytes)}`);
      await foldersClient.add(props.token, file);
      emit("added");
    }
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="folder-files">
    <StateMessage v-if="!files.length" kind="empty">No files yet.</StateMessage>
    <ul v-else class="files">
      <li v-for="file in files" :key="file.id" class="file">
        <div class="what">
          <a class="name" :href="foldersClient.downloadUrl(token, file.id)" :download="file.name">{{ file.name }}</a>
          <span class="muted">{{ formatBytes(file.size) }} · {{ formatUtc(file.created_at) }}</span>
        </div>
        <button v-if="removable" type="button" class="pill-btn ghost" :aria-label="`Remove ${file.name}`" @click="emit('remove', file)">Remove</button>
      </li>
    </ul>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <input ref="picker" type="file" multiple hidden :disabled="busy" aria-label="Add files" @change="upload" />
    <button type="button" class="pill-btn primary add" :disabled="busy" :aria-busy="busy" @click="picker?.click()">
      Add files
    </button>
    <p class="muted hint">Up to {{ formatBytes(maxFileBytes) }} per file. Anyone with the link can add and download files; only the owner can remove them.</p>
  </div>
</template>

<style scoped>
.folder-files { display: flex; flex-direction: column; gap: 10px; }
.files { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.file { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); }
.what { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name { font-weight: 600; overflow-wrap: anywhere; color: var(--accent); }
.muted { color: var(--muted); font-size: .85em; }
.hint { margin: 0; }
.error { margin: 0; color: var(--danger); }
.add { align-self: flex-start; }
@media (max-width: 767px) {
  .file { flex-direction: column; align-items: stretch; }
  .file button, .add { min-height: 44px; min-width: 44px; }
}
</style>
