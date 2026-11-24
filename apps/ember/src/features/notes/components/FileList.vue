<script setup lang="ts">
import ListRow from "../../../components/ui/lists/ListRow.vue";
import SearchField from "../../../components/ui/lists/SearchField.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { formatUtc } from "../../../utils/time";
import type { BrainFileRow, SearchHit } from "../api/BrainClient";

/** The left pane of the Notes page: search, the folder buttons and the file rows. It only shows what it is given;
 * the page filters, searches and decides what opens. */
defineProps<{
  rows: (BrainFileRow | SearchHit)[];
  folders: string[];
  selectedId: string | null;
  /** A file the user started but has not saved: shown first. "" means no title yet. */
  draftTitle: string | null;
  /** The rows are search results: the folder buttons do not apply. */
  isSearch: boolean;
  searchBusy: boolean;
  searchError: string;
  disabled: boolean;
}>();

const query = defineModel<string>("query", { required: true });
const folder = defineModel<string | null>("folder", { required: true });
defineEmits<{ select: [id: string] }>();
</script>

<template>
  <div class="file-list">
    <div class="list-heading">
      <span>{{ isSearch ? "Search results" : "Files" }}</span>
      <span>{{ rows.length }} {{ rows.length === 1 ? "file" : "files" }}</span>
    </div>
    <SearchField v-model="query" class="search" label="Search files" placeholder="Search titles, tags and text…" maxlength="200" />
    <p v-if="searchBusy" class="muted note" role="status">Searching …</p>
    <p v-if="searchError" class="error note" role="alert">{{ searchError }}</p>
    <div class="list-scroll pane-scroll">
      <div v-if="folders.length && !isSearch" class="folders" role="group" aria-label="Folders">
        <button type="button" class="chip" :class="{ active: folder === null }" :aria-pressed="folder === null" @click="folder = null">All</button>
        <button type="button" class="chip" :class="{ active: folder === '' }" :aria-pressed="folder === ''" @click="folder = ''">No folder</button>
        <button
          v-for="name in folders" :key="name" type="button" class="chip" :class="{ active: folder === name }"
          :aria-pressed="folder === name" @click="folder = name"
        >{{ name }}</button>
      </div>
      <StateMessage v-if="rows.length === 0 && draftTitle === null && !searchBusy" kind="empty" :title="isSearch ? 'No files match your search.' : undefined">
        {{ isSearch ? "Try other words." : "No files here yet." }}
      </StateMessage>
      <ul v-else class="list" aria-label="Files">
        <li v-if="draftTitle !== null">
          <ListRow class="file-row" active>
            <span class="title">{{ draftTitle.trim() || "New file" }}</span>
            <span class="muted">Not saved yet</span>
          </ListRow>
        </li>
        <li v-for="row in rows" :key="row.id">
          <ListRow class="file-row" :active="row.id === selectedId" :data-file-id="row.id" :disabled="disabled" @click="$emit('select', row.id)">
            <span class="title">{{ row.title }}</span>
            <span v-if="'snippet' in row && row.snippet" class="snippet">{{ row.snippet }}</span>
            <span v-if="row.folder" class="muted path">{{ row.folder }}</span>
            <span class="badges">
              <span v-for="tag in row.tags" :key="tag" class="status-badge">{{ tag }}</span>
              <span v-if="row.source === 'automatic'" class="status-badge agent-mark"><svg class="line-icon" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>Agent file</span>
              <span v-else-if="row.source === 'shared'" class="status-badge">Shared by {{ row.shared_from || "another account" }}</span>
              <span v-if="row.agent_editable && row.source !== 'automatic'" class="status-badge">Agents can edit</span>
              <span v-if="row.edited" class="status-badge">Edited</span>
            </span>
            <span class="muted when">{{ formatUtc(row.updated_at) }}</span>
          </ListRow>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.file-list { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.list-heading { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 8px; padding: 0 4px; font-size: .8em; color: var(--muted); }
.search { margin-bottom: 10px; flex-shrink: 0; }
.note { margin: 0 4px 8px; font-size: .85em; }
.folders { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; flex-shrink: 0; }
.list-scroll { flex: 1; min-height: 0; }
.list { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; }
.list li { border-bottom: 1px solid var(--border); }
.title { font-weight: 600; overflow-wrap: anywhere; }
.snippet { color: var(--muted); overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.path, .when { font-size: .8em; overflow-wrap: anywhere; }
.badges { display: flex; flex-wrap: wrap; gap: 4px; }
.agent-mark { display: inline-flex; align-items: center; gap: 4px; border-color: var(--warning); }
.agent-mark .line-icon { color: var(--warning); }
@media (max-width: 767px) {
  .folders .chip, .list-scroll :deep(button) { min-width: 44px; min-height: 44px; }
  .file-row { min-height: 88px; }
}
</style>
