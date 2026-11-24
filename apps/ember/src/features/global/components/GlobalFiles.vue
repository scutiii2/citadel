<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import ListRow from "../../../components/ui/lists/ListRow.vue";
import SearchField from "../../../components/ui/lists/SearchField.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import type { BrainFileRow, SearchHit } from "../../notes/api/BrainClient";
import { globalClient } from "../api/GlobalClient";
import GlobalFileDialog from "./GlobalFileDialog.vue";

defineProps<{ canWrite: boolean }>();
const auth = useAuthStore();
const fallbackLimit = 20_000;
const maxChars = ref(fallbackLimit);
const status = ref<"loading" | "ready" | "error">("loading");
const error = ref("");
const files = ref<BrainFileRow[]>([]);
const folders = ref<string[]>([]);
const folder = ref<string | null>(null);
const query = ref("");
const hits = ref<SearchHit[] | null>(null);
const searchError = ref("");
const opened = ref<{ id: string | null } | null>(null);
const note = ref("");
let active = true;
let listings = 0;
let searches = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

async function load(): Promise<void> {
  if (!active || !auth.account) return;
  const run = ++listings;
  status.value = "loading";
  error.value = "";
  try {
    const result = await globalClient.list(folder.value ?? undefined);
    if (run !== listings) return;
    files.value = result.files;
    folders.value = result.folders;
    status.value = "ready";
  } catch (err) {
    if (run !== listings) return;
    error.value = errorMessage(err);
    status.value = "error";
  }
}

function cancelSearch(): void {
  searches++;
  clearTimeout(timer);
  hits.value = null;
  searchError.value = "";
}
async function search(): Promise<void> {
  cancelSearch();
  const q = query.value.trim();
  if (!q || !auth.account) return;
  const run = searches;
  try {
    const result = await globalClient.search(q);
    if (run === searches) hits.value = result;
  } catch (err) {
    if (run === searches) searchError.value = errorMessage(err);
  }
}

watch(folder, load, { flush: "sync" });
watch(query, (text) => {
  cancelSearch();
  if (text.trim() && auth.account) timer = setTimeout(search, 300);
}, { flush: "sync" });

function clear(): void {
  active = false;
  folder.value = null;
  query.value = "";
  listings++;
  cancelSearch();
  files.value = [];
  folders.value = [];
  opened.value = null;
  maxChars.value = fallbackLimit;
  status.value = "ready";
  error.value = note.value = "";
}
watch(() => auth.account?.id, clear, { flush: "sync" });
onBeforeUnmount(clear);

onMounted(async () => {
  if (!auth.account) return;
  const account = auth.account;
  void load();
  const summary = await globalClient.summary().catch(() => null);
  if (active && auth.account?.id === account.id && summary) maxChars.value = summary.max_record_chars;
});
function finished(message: string): void {
  opened.value = null;
  note.value = message;
  void load();
  if (query.value.trim()) void search();
}
</script>

<template>
  <div class="global-files">
    <div class="toolbar">
      <SearchField v-model="query" class="search" label="Search global files" maxlength="200" />
      <button v-if="canWrite" type="button" class="pill-btn primary" @click="opened = { id: null }">New file</button>
    </div>
    <div v-if="!query.trim() && folders.length" class="toolbar" role="group" aria-label="Folders">
      <button type="button" class="chip" :aria-pressed="folder === null" @click="folder = null">All files</button>
      <button v-for="entry in folders" :key="entry" type="button" class="chip" :aria-pressed="entry === folder" @click="folder = entry">{{ entry }}</button>
    </div>
    <p v-if="note" role="status" class="feedback"><span aria-hidden="true">✓</span> {{ note }}</p>
    <template v-if="query.trim()">
      <StateMessage v-if="searchError" kind="error" class="load-state" @retry="search"><span class="warning" aria-hidden="true">⚠</span> Could not search files. {{ searchError }}</StateMessage>
      <StateMessage v-else-if="hits === null" kind="loading">Searching files…</StateMessage>
      <StateMessage v-else-if="!hits.length" kind="empty">No files match your search.</StateMessage>
    </template>
    <template v-else>
      <StateMessage v-if="status === 'loading'" kind="loading">Loading files…</StateMessage>
      <StateMessage v-else-if="status === 'error'" kind="error" class="load-state" @retry="load"><span class="warning" aria-hidden="true">⚠</span> Could not load files. {{ error }}</StateMessage>
      <StateMessage v-else-if="!files.length" kind="empty">{{ folder ? "No files in this folder." : "No files yet." }}</StateMessage>
    </template>
    <ul v-if="query.trim() ? hits?.length : status === 'ready' && files.length" class="file-list">
      <li v-for="file in (query.trim() ? hits : files)" :key="file.id">
        <ListRow :data-file-id="file.id" :active="opened?.id === file.id" @click="opened = { id: file.id }">
          <strong>{{ file.title }}</strong>
          <span class="meta">{{ file.folder || "Top folder" }} · {{ formatUtc(file.updated_at) }} · {{ file.chars }} characters</span>
          <span v-if="'snippet' in file" class="meta">{{ file.snippet }}</span>
        </ListRow>
      </li>
    </ul>
    <GlobalFileDialog v-if="opened" :open="true" :file-id="opened.id" :can-write="canWrite" :max-chars="maxChars" @close="opened = null" @done="finished" />
  </div>
</template>

<style scoped>
.global-files { display: grid; gap: 12px; min-width: 0; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.toolbar button, .search, .load-state :deep(button) { min-height: 44px; }
.search { flex: 1 1 220px; }
.chip { overflow-wrap: anywhere; max-width: 100%; }
.chip[aria-pressed="true"] { border-color: var(--accent); }
.file-list { list-style: none; padding: 0; margin: 0; overflow-wrap: anywhere; }
.file-list li + li { border-top: 1px solid var(--border); }
.feedback { margin: 0; color: var(--text); }
.meta { color: var(--muted); }
.global-files .load-state { color: var(--text); }
.warning { color: var(--warning); }
</style>
