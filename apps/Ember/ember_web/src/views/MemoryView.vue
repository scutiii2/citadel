<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, getCurrentInstance, onMounted, onUnmounted, ref, watch } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import { MEMORY_MAX, MEMORY_TEXT_MAX, memoryClient, type MemoryNote } from "../api/MemoryClient";
import BaseModal from "../components/BaseModal.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

const memories = ref<MemoryNote[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");
const query = ref("");
const visible = ref(20);
const matches = computed(() => {
  const words = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return memories.value.filter((memory) => words.every((word) => memory.text.toLocaleLowerCase().includes(word)));
});
const shown = computed(() => matches.value.slice(0, visible.value));
watch(query, () => { visible.value = 20; }, { flush: "sync" });

async function load(): Promise<void> {
  if (!loading.value) loading.value = true;
  loadError.value = "";
  try { memories.value = await memoryClient.list(); }
  catch (error) { loadError.value = errorMessage(error); }
  finally { loading.value = false; }
}
onMounted(load);

const editorOpen = ref(false);
const editing = ref<MemoryNote | null>(null);
const text = ref("");
const formError = ref("");
const saving = ref(false);
const dirty = computed(() => editorOpen.value && text.value !== (editing.value?.text ?? ""));
const canSave = computed(() => dirty.value && text.value.trim() !== "" && text.value.length <= MEMORY_TEXT_MAX && !saving.value);
const discardOpen = ref(false);
let leaveAnswer: ((leave: boolean) => void) | null = null;

function openEditor(memory: MemoryNote | null = null): void {
  editing.value = memory;
  text.value = memory?.text ?? "";
  formError.value = "";
  editorOpen.value = true;
}
function closeEditor(): void {
  if (saving.value) return;
  if (dirty.value) discardOpen.value = true;
  else editorOpen.value = false;
}
function answerDiscard(discard: boolean): void {
  discardOpen.value = false;
  if (discard) editorOpen.value = false;
  leaveAnswer?.(discard);
  leaveAnswer = null;
}
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) {
  onBeforeRouteLeave(() => {
    if (saving.value || removing.value) return false;
    if (!dirty.value) return true;
    discardOpen.value = true;
    return new Promise<boolean>((resolve) => { leaveAnswer = resolve; });
  });
}
function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value || saving.value || removing.value) { event.preventDefault(); event.returnValue = ""; }
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onUnmounted(() => { window.removeEventListener("beforeunload", beforeUnload); leaveAnswer?.(false); });

async function save(): Promise<void> {
  if (!canSave.value) return;
  saving.value = true;
  formError.value = "";
  try {
    const note = editing.value
      ? await memoryClient.update(editing.value.id, text.value, editing.value.text)
      : await memoryClient.create(text.value);
    memories.value = [note, ...memories.value.filter((memory) => memory.id !== note.id)];
    memories.value.sort((a, b) => b.id - a.id);
    query.value = "";
    // Keep the saved item visible, including an older memory edited beyond page one.
    visible.value = Math.max(20, memories.value.findIndex((memory) => memory.id === note.id) + 1);
    editorOpen.value = false;
    notice.value = "Memory saved.";
  } catch (error) { formError.value = errorMessage(error); }
  finally { saving.value = false; }
}

const deleting = ref<MemoryNote | null>(null);
const removing = ref(false);
const removeError = ref("");
function askDelete(memory: MemoryNote): void { deleting.value = memory; removeError.value = ""; }
async function remove(): Promise<void> {
  if (!deleting.value || removing.value) return;
  removing.value = true;
  removeError.value = "";
  try {
    await memoryClient.remove(deleting.value.id);
    memories.value = memories.value.filter((memory) => memory.id !== deleting.value!.id);
    if (editing.value?.id === deleting.value.id) editorOpen.value = false;
    deleting.value = null;
    notice.value = "Memory deleted.";
  } catch (error) { removeError.value = errorMessage(error); }
  finally { removing.value = false; }
}
</script>

<template>
  <PageLayout title="Memory" description="Review the context Ember remembers about you." class="memory info-content">
    <template #actions>
      <button type="button" class="primary" :disabled="loading || !!loadError || memories.length >= MEMORY_MAX" @click="openEditor()">Add memory</button>
    </template>
    <template #toolbar>
      <label v-if="!loading && !loadError" class="page-search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
        <input v-model="query" type="search" aria-label="Search memories" placeholder="Search memories…" />
      </label>
    </template>
    <div class="column">
      <p v-if="notice" class="muted" role="status">{{ notice }}</p>
      <p v-if="loading" class="muted" role="status">Loading memories…</p>
      <div v-else-if="loadError" class="load-error" role="alert">
        <p>Could not load memories: {{ loadError }}</p>
        <button type="button" class="chip" @click="load">Try again</button>
      </div>
      <template v-else>
        <div class="list-heading">
          <span>Saved memories</span>
          <span>{{ query.trim() ? `${matches.length} matches · ` : "" }}{{ memories.length }}/{{ MEMORY_MAX }} memories</span>
        </div>
        <div v-if="memories.length === 0" class="empty">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4c-5-5-10 2-6 5-6 2-2 9 2 7-1 6 4 6 4 2V4zm0 0c5-5 10 2 6 5 6 2 2 9-2 7 1 6-4 6-4 2" /></svg>
          <h3>No saved memories yet.</h3>
          <p>Add a useful fact, preference, or instruction for Ember to remember.</p>
        </div>
        <div v-else-if="matches.length === 0" class="empty">
          <h3>No memories match your search.</h3>
          <p>Try a different word or clear your search.</p>
          <button type="button" class="chip" @click="query = ''">Clear search</button>
        </div>
        <div v-else class="memory-list" aria-label="Saved memories">
          <article v-for="(memory, index) in shown" :key="memory.id" class="memory-row">
            <span class="row-number" aria-hidden="true">{{ String(index + 1).padStart(2, "0") }}</span>
            <div class="memory-copy">
              <p class="memory-text">{{ memory.text }}</p>
              <p class="memory-date">Created <time :datetime="memory.created_at">{{ new Date(memory.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) }}</time></p>
            </div>
            <button type="button" class="chip edit-memory" :aria-label="`Edit memory ${memory.id}`" :data-label="`Edit memory ${memory.id}`" @click="openEditor(memory)">
              <span>Edit</span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l5-1L20 8a2.8 2.8 0 0 0-4-4L5 15z" /></svg>
            </button>
          </article>
        </div>
        <footer v-if="matches.length" class="pagination">
          <p class="muted">Showing {{ shown.length }} of {{ matches.length }} memories</p>
          <span class="sort-label">Newest first</span>
          <button v-if="shown.length < matches.length" type="button" class="chip" @click="visible += 20">Load more</button>
        </footer>
        <p v-if="memories.length >= MEMORY_MAX" class="muted">Memory is full. Delete a memory before adding another.</p>
        <p class="memory-help"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7v.2" /></svg><span>Keep each memory to one useful fact, preference, or instruction. Edit anything that no longer fits.</span></p>
      </template>
    </div>
    <BaseModal class="memory-editor" :open="editorOpen" :title="editing ? 'Edit memory' : 'Add memory'" @close="closeEditor">
      <form class="memory-form info-page" @submit.prevent="save">
        <p class="page-description">Save one short fact, preference or instruction for Ember to remember.</p>
        <label for="memory-text">Memory</label>
        <textarea id="memory-text" v-model="text" rows="5" :maxlength="MEMORY_TEXT_MAX" :disabled="saving" autofocus />
        <p class="character-count muted">{{ text.length }}/{{ MEMORY_TEXT_MAX }} characters</p>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="form-actions">
          <button type="button" class="chip" :disabled="saving" @click="closeEditor">Cancel</button>
          <button type="submit" class="primary" :disabled="!canSave" :aria-busy="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
        </div>
        <div v-if="editing" class="danger-zone">
          <span>Remove this context</span>
          <button type="button" class="danger" :aria-label="`Delete memory ${editing.id}`" :disabled="saving || removing" @click="askDelete(editing)">Delete memory</button>
        </div>
      </form>
    </BaseModal>
    <ConfirmModal :open="deleting !== null" title="Delete this memory?"
      :message="removeError || 'Ember will no longer remember this. This cannot be undone.'"
      confirm-label="Delete memory" danger :busy="removing" @confirm="remove" @close="!removing && (deleting = null)" />
    <ConfirmModal :open="discardOpen" title="Discard your changes?" message="This memory has changes you have not saved."
      confirm-label="Discard" danger @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
.page-search { margin: 0; }
.list-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin: 0 2px 12px; color: var(--muted); font-size: .75em; }
.list-heading > :first-child { text-transform: uppercase; letter-spacing: .08em; }
.memory-list { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.memory-row { display: flex; align-items: center; gap: 16px; padding: 18px 20px; background: var(--bg); transition: background .15s ease; }
.memory-row + .memory-row { border-top: 1px solid var(--border); }
.memory-row:hover { background: color-mix(in srgb, var(--surface) 55%, var(--bg)); }
.row-number { width: 22px; flex-shrink: 0; align-self: flex-start; padding-top: 3px; font-size: .75em; font-variant-numeric: tabular-nums; color: var(--muted); }
.memory-copy { flex: 1; min-width: 0; }
.memory-text { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; line-height: 1.7; }
.memory-date { margin: 6px 0 0; color: var(--muted); font-size: .75em; }
button.edit-memory { flex-shrink: 0; padding: 5px 14px; min-height: 32px; }
.edit-memory svg { display: none; }
.edit-memory svg, .empty svg, .memory-help svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.pagination { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 16px; color: var(--muted); font-size: .8em; }
.pagination p { margin: 0; }
.pagination .sort-label { margin-left: auto; }
.empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 20px; border: 1px solid var(--border); border-radius: var(--radius-lg); text-align: center; color: var(--muted); }
.empty svg { width: 34px; height: 34px; color: var(--accent); }
.empty h3 { color: var(--text); }
.empty p { margin: 0; font-size: .9em; }
.memory-help { display: flex; align-items: flex-start; gap: 9px; margin: 24px 0 0; padding-top: 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: .8em; }
.memory-help svg { width: 16px; height: 16px; margin-top: 2px; flex-shrink: 0; color: var(--accent); }
.load-error { color: var(--danger); }
.memory-form { display: flex; flex-direction: column; gap: 8px; overflow: visible; }
.memory-form .page-description { margin: 0 0 12px; }
.memory-form label { font-size: .9em; font-weight: 600; }
.memory-form textarea { width: 100%; min-height: 140px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--surface); font: inherit; line-height: 1.7; resize: vertical; }
.character-count { margin: 0; font-size: .75em; text-align: right; }
.form-actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 16px; }
.form-actions button { min-height: 40px; }
.form-actions button[aria-busy="true"]::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 7px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); vertical-align: -1px; animation: memory-save-spin .7s linear infinite; }
@keyframes memory-save-spin { to { transform: rotate(360deg); } }
.danger-zone { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-top: 16px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-lg); font-size: .85em; }
button:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 767px) {
  .memory :deep(.page-head) { flex-direction: row; gap: 12px; }
  .memory :deep(.page-description) { max-width: 200px; }
  .memory :deep(.page-actions) { flex-shrink: 0; }
  .memory :deep(.page-actions button) { min-height: 44px; }
  .memory-list { border: 0; border-radius: 0; }
  .memory-row { align-items: flex-start; gap: 12px; padding: 18px 0; }
  .row-number { display: none; }
  .memory-date { margin-top: 9px; }
  button.edit-memory { position: relative; display: grid; place-items: center; width: 44px; min-height: 44px; padding: 0; border-color: transparent; border-radius: var(--radius-md); }
  button.edit-memory:hover { border-color: var(--border); }
  .edit-memory:is(:hover, :focus-visible)::after { content: attr(data-label); position: absolute; right: calc(100% + 8px); top: 50%; transform: translateY(-50%); padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); color: var(--text); font-size: .75em; white-space: nowrap; pointer-events: none; z-index: 1; }
  .edit-memory span { display: none; }
  .edit-memory svg { display: block; width: 18px; height: 18px; }
  .pagination .sort-label { display: none; }
  dialog.memory-editor {
    position: fixed;
    inset: auto 0 var(--rail-height);
    width: 100%;
    max-width: none;
    max-height: calc(100dvh - var(--rail-height) - env(safe-area-inset-top, 0px) - 16px);
    margin: 0;
    padding: 22px 20px;
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
  .memory-form textarea { font-size: max(1em, 16px); }
  .form-actions button { min-height: 44px; }
  .form-actions .primary { flex: 1; }
}
</style>
